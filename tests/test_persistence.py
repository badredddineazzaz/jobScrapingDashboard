"""Persistence and conservative deduplication tests."""

from typing import Iterator, Optional

from sqlalchemy import func, select

from jobscraper.db.database import create_database_engine, create_session_factory
from jobscraper.db.models import Base, Job, JobSource, SearchRun, SearchRunJob
from jobscraper.models.job import JobOffer, SearchCriteria
from jobscraper.scrapers.base import BaseScraper
from jobscraper.services.persistence import PersistentSearchRunner
from jobscraper.services.search import SearchService


def offer(source: str, external_id: str, url: str) -> JobOffer:
    return JobOffer(
        id=external_id,
        source=source,
        url=url,
        title="Senior Python Engineer",
        company="Example SAS",
        location="Paris, France",
        description="A detailed description",
    )


class FixtureScraper(BaseScraper):
    name = "fixture"

    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        yield offer(
            self.name,
            "fixture_123",
            "https://example.com/jobs/123?utm_source=test",
        )

    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        return None


class DuplicateScraper(BaseScraper):
    name = "duplicate"

    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        yield offer(
            self.name,
            "duplicate_456",
            "https://another.example/jobs/456",
        )

    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        return None


def build_runner(factories):
    engine = create_database_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    runner = PersistentSearchRunner(
        SearchService(scraper_factories=factories), session_factory
    )
    return runner, session_factory


def scalar_count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_repeated_search_creates_two_runs_but_one_canonical_job() -> None:
    runner, session_factory = build_runner({"fixture": FixtureScraper})

    first_run_id = runner.run(SearchCriteria())
    second_run_id = runner.run(SearchCriteria())

    assert first_run_id != second_run_id
    with session_factory() as session:
        assert scalar_count(session, Job) == 1
        assert scalar_count(session, JobSource) == 1
        assert scalar_count(session, SearchRun) == 2
        assert scalar_count(session, SearchRunJob) == 2
        runs = session.scalars(select(SearchRun)).all()
        assert all(run.status == "completed" for run in runs)
        assert all(run.total_jobs == 1 for run in runs)


def test_matching_fingerprint_merges_cross_source_duplicates() -> None:
    runner, session_factory = build_runner(
        {"fixture": FixtureScraper, "duplicate": DuplicateScraper}
    )

    runner.run(SearchCriteria())

    with session_factory() as session:
        assert scalar_count(session, Job) == 1
        assert scalar_count(session, JobSource) == 2
        job = session.scalar(select(Job))
        assert job is not None
        assert {source.source for source in job.sources} == {
            "fixture",
            "duplicate",
        }


def test_tracking_query_parameters_do_not_create_a_duplicate() -> None:
    runner, session_factory = build_runner({"fixture": FixtureScraper})
    runner.run(SearchCriteria())

    changed_url_offer = offer(
        "fixture",
        "fixture_123",
        "https://example.com/jobs/123?utm_campaign=second-run",
    )

    with session_factory() as session:
        from jobscraper.db.repositories import JobRepository

        JobRepository(session).upsert(changed_url_offer)
        session.commit()
        assert scalar_count(session, Job) == 1
        assert scalar_count(session, JobSource) == 1
