"""Persist a reusable search service run and its discovered jobs."""

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session, sessionmaker

from jobscraper.backend.ports import ScraperGateway
from jobscraper.db.models import SearchRun, SearchRunSource
from jobscraper.db.repositories import JobRepository, SearchRunRepository
from jobscraper.models.job import SearchCriteria
from jobscraper.services.search import (
    CancellationCheck,
    ProgressCallback,
    SearchResult,
)


class PersistentSearchRunner:
    """Run a search and atomically persist its outcome."""

    def __init__(
        self,
        search_service: ScraperGateway,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.search_service = search_service
        self.session_factory = session_factory

    def run(
        self,
        criteria: SearchCriteria,
        sources: Optional[Iterable[str]] = None,
        include_details: bool = False,
    ) -> str:
        selected_sources = self.search_service.resolve_sources(sources)
        run_id = self.create_run(criteria, selected_sources)
        self.execute_run(run_id, criteria, selected_sources, include_details)
        return run_id

    def execute_run(
        self,
        run_id: str,
        criteria: SearchCriteria,
        sources: Iterable[str],
        include_details: bool = False,
        on_event: Optional[ProgressCallback] = None,
        should_cancel: Optional[CancellationCheck] = None,
    ) -> SearchResult:
        try:
            result = self.search_service.search(
                criteria,
                sources=sources,
                include_details=include_details,
                on_event=on_event,
                should_cancel=should_cancel,
            )
            self.complete_run(run_id, result)
        except Exception as exc:
            self.fail_run(run_id, str(exc))
            raise
        return result

    def create_run(
        self, criteria: SearchCriteria, selected_sources: Iterable[str]
    ) -> str:
        with self.session_factory() as session:
            search_run = SearchRun(
                criteria=criteria.model_dump(mode="json"),
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            session.add(search_run)
            session.flush()
            for source in selected_sources:
                session.add(
                    SearchRunSource(
                        search_run_id=search_run.id,
                        source=source,
                        status="running",
                        started_at=datetime.now(timezone.utc),
                    )
                )
            session.commit()
            return search_run.id

    def complete_run(self, run_id: str, result: SearchResult) -> None:
        with self.session_factory() as session:
            search_run = session.get(SearchRun, run_id)
            if search_run is None:
                raise RuntimeError(f"Search run {run_id} no longer exists")

            job_repository = JobRepository(session)
            run_repository = SearchRunRepository(session)
            for offer in result.jobs:
                job = job_repository.upsert(offer)
                run_repository.add_job(search_run, job)

            source_rows = {row.source: row for row in search_run.sources}
            now = datetime.now(timezone.utc)
            for source, source_result in result.sources.items():
                row = source_rows[source]
                row.status = source_result.status.value
                row.job_count = source_result.job_count
                row.error = source_result.error
                row.completed_at = now

            search_run.total_jobs = len(result.jobs)
            if result.cancelled:
                search_run.status = "cancelled"
            else:
                search_run.status = (
                    "completed_with_errors" if result.errors else "completed"
                )
            search_run.completed_at = now
            session.commit()

    def fail_run(self, run_id: str, error: str) -> None:
        with self.session_factory() as session:
            search_run = session.get(SearchRun, run_id)
            if search_run is not None:
                search_run.status = "failed"
                search_run.error = error
                search_run.completed_at = datetime.now(timezone.utc)
                session.commit()
