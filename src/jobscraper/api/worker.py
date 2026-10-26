"""Local background execution and live-event broker.

This single-instance worker is deliberately replaceable. The API contract does
not depend on its implementation, so a Redis-backed adapter can be introduced
for horizontally scaled deployments.
"""

import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, Iterable, Iterator, List

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobscraper.db.models import Notification, SearchRun, SearchRunSource
from jobscraper.models.job import SearchCriteria
from jobscraper.services.persistence import PersistentSearchRunner
from jobscraper.services.search import SearchEvent, SearchEventType


TERMINAL_EVENTS = {
    SearchEventType.SEARCH_COMPLETED.value,
    SearchEventType.SEARCH_CANCELLED.value,
    "search_failed",
}


class SearchRunManager:
    """Dispatch local jobs and publish their progress to SSE subscribers."""

    def __init__(
        self,
        runner: PersistentSearchRunner,
        session_factory: sessionmaker[Session],
        max_workers: int = 2,
    ) -> None:
        self.runner = runner
        self.session_factory = session_factory
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="jobscraper"
        )
        self._cancelled: set[str] = set()
        self._history: Dict[str, List[dict]] = {}
        self._subscribers: Dict[str, List[queue.Queue]] = {}
        self._lock = threading.Lock()

    def start(
        self,
        criteria: SearchCriteria,
        sources: Iterable[str],
        include_details: bool,
    ) -> str:
        selected = self.runner.search_service.resolve_sources(sources)
        run_id = self.runner.create_run(criteria, selected)
        with self._lock:
            self._history[run_id] = []
        self.executor.submit(
            self._execute, run_id, criteria, selected, include_details
        )
        return run_id

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            self._cancelled.add(run_id)
        with self.session_factory() as session:
            return session.get(SearchRun, run_id) is not None

    def is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._cancelled

    def events(self, run_id: str) -> Iterator[dict]:
        subscriber: queue.Queue = queue.Queue()
        with self._lock:
            history = list(self._history.get(run_id, []))
            self._subscribers.setdefault(run_id, []).append(subscriber)
        try:
            for event in history:
                yield event
                if event["type"] in TERMINAL_EVENTS:
                    return
            while True:
                try:
                    event = subscriber.get(timeout=15)
                except queue.Empty:
                    yield {"type": "heartbeat"}
                    continue
                yield event
                if event["type"] in TERMINAL_EVENTS:
                    return
        finally:
            with self._lock:
                subscribers = self._subscribers.get(run_id, [])
                if subscriber in subscribers:
                    subscribers.remove(subscriber)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _execute(
        self,
        run_id: str,
        criteria: SearchCriteria,
        sources: Iterable[str],
        include_details: bool,
    ) -> None:
        terminal_event: List[SearchEvent] = []

        def handle_event(event: SearchEvent) -> None:
            if event.type in {
                SearchEventType.SEARCH_COMPLETED,
                SearchEventType.SEARCH_CANCELLED,
            }:
                terminal_event.append(event)
            else:
                self._on_event(run_id, event)

        try:
            result = self.runner.execute_run(
                run_id,
                criteria,
                sources,
                include_details,
                on_event=handle_event,
                should_cancel=lambda: self.is_cancelled(run_id),
            )
            for event in terminal_event:
                self._on_event(run_id, event)
            with self.session_factory() as session:
                session.add(
                    Notification(
                        kind="search_complete",
                        title="Job search complete",
                        message=f"{len(result.jobs)} jobs were collected.",
                        entity_type="search_run",
                        entity_id=run_id,
                    )
                )
                session.commit()
        except Exception as exc:
            self._publish(
                run_id, {"type": "search_failed", "error": str(exc)}
            )

    def _on_event(self, run_id: str, event: SearchEvent) -> None:
        payload = jsonable_encoder(asdict(event))
        payload["type"] = event.type.value
        self._update_progress(run_id, event)
        self._publish(run_id, payload)

    def _publish(self, run_id: str, event: dict) -> None:
        with self._lock:
            self._history.setdefault(run_id, []).append(event)
            subscribers = list(self._subscribers.get(run_id, []))
        for subscriber in subscribers:
            subscriber.put(event)

    def _update_progress(self, run_id: str, event: SearchEvent) -> None:
        with self.session_factory() as session:
            search_run = session.get(SearchRun, run_id)
            if search_run is None:
                return
            search_run.total_jobs = event.total_job_count
            if event.source:
                source_row = session.scalar(
                    select(SearchRunSource).where(
                        SearchRunSource.search_run_id == run_id,
                        SearchRunSource.source == event.source,
                    )
                )
                if source_row is not None:
                    source_row.job_count = event.source_job_count
                    if event.type == SearchEventType.SOURCE_STARTED:
                        source_row.status = "running"
                    elif event.type == SearchEventType.SOURCE_COMPLETED:
                        source_row.status = "completed"
                        source_row.completed_at = datetime.now(timezone.utc)
                    elif event.type == SearchEventType.SOURCE_FAILED:
                        source_row.status = "failed"
                        source_row.error = event.error
                        source_row.completed_at = datetime.now(timezone.utc)
            session.commit()
