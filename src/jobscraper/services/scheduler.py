"""Durable database scheduler for saved searches."""

import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobscraper.api.worker import SearchRunManager
from jobscraper.db.models import Notification, Search
from jobscraper.models.job import SearchCriteria


class SavedSearchScheduler:
    """Poll due saved searches and dispatch them through the run manager."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        run_manager: SearchRunManager,
        poll_seconds: int = 30,
    ) -> None:
        self.session_factory = session_factory
        self.run_manager = run_manager
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop, name="saved-search-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def run_due(self, now: Optional[datetime] = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        dispatched: list[str] = []
        with self.session_factory() as session:
            searches = session.scalars(
                select(Search).where(
                    Search.schedule_enabled.is_(True),
                    Search.next_run_at.is_not(None),
                    Search.next_run_at <= now,
                )
            ).all()
            for saved_search in searches:
                interval = saved_search.schedule_interval_minutes or 1440
                saved_search.last_run_at = now
                saved_search.next_run_at = now + timedelta(minutes=interval)
                criteria = SearchCriteria.model_validate(saved_search.criteria)
                run_id = self.run_manager.start(
                    criteria,
                    saved_search.sources or ["all"],
                    saved_search.include_details,
                )
                session.add(
                    Notification(
                        kind="scheduled_search",
                        title=f"Scheduled search started: {saved_search.name}",
                        message="The saved search is running in the background.",
                        entity_type="search_run",
                        entity_id=run_id,
                    )
                )
                dispatched.append(run_id)
            session.commit()
        return dispatched

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            try:
                self.run_due()
            except Exception:
                logger.exception("Saved-search scheduler iteration failed")
