"""Integration tests for the Phase 3 API contract and background manager."""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import select

from jobscraper.api.app import create_app
from jobscraper.api.schemas import (
    ApplicationCreate,
    ApplicationUpdate,
    SavedSearchCreate,
    TaskCreate,
)
from jobscraper.db.models import Job, Notification, Search, SearchRun
from jobscraper.models.job import JobOffer, SearchCriteria
from jobscraper.scrapers.base import BaseScraper
from jobscraper.services.search import SearchService


class ApiFixtureScraper(BaseScraper):
    name = "fixture"

    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        yield JobOffer(
            id="fixture_api_1",
            source=self.name,
            url="https://example.com/jobs/api-1",
            title="Python API Engineer",
            company="API Company",
            location="Paris, France",
            description="FastAPI and SQLAlchemy",
            remote=True,
        )

    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        return None


class SlowFixtureScraper(BaseScraper):
    name = "slow"

    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        for index in range(30):
            time.sleep(0.01)
            yield JobOffer(
                id=f"slow_{index}",
                source=self.name,
                url=f"https://example.com/jobs/slow-{index}",
                title=f"Slow Job {index}",
                company="Slow Company",
                location="Lyon, France",
            )

    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        return None


def make_app(tmp_path: Path, factories):
    database_url = f"sqlite:///{tmp_path / 'api.db'}"
    service = SearchService(scraper_factories=factories)
    return create_app(database_url, service, initialize_schema=True)


def wait_for_terminal(app, run_id: str) -> SearchRun:
    for _ in range(100):
        with app.state.session_factory() as session:
            search_run = session.get(SearchRun, run_id)
            if search_run is not None and search_run.status in {
                "completed",
                "completed_with_errors",
                "failed",
                "cancelled",
            }:
                session.expunge(search_run)
                return search_run
        time.sleep(0.01)
    raise AssertionError("search run did not finish")


def test_openapi_exposes_phase_three_endpoints(tmp_path: Path) -> None:
    app = make_app(tmp_path, {"fixture": ApiFixtureScraper})
    paths = app.openapi()["paths"]

    assert "/api/health" in paths
    assert "/api/sources" in paths
    assert "/api/search-runs" in paths
    assert "/api/search-runs/{run_id}" in paths
    assert "/api/search-runs/{run_id}/cancel" in paths
    assert "/api/search-runs/{run_id}/events" in paths
    assert "/api/jobs" in paths
    assert "/api/jobs/{job_id}" in paths
    assert "/api/applications" in paths
    assert "/api/applications/{application_id}" in paths
    assert "/api/applications/{application_id}/tasks" in paths
    assert "/api/analytics/overview" in paths
    assert "/api/saved-searches" in paths
    assert "/api/saved-searches/{search_id}/run" in paths
    assert "/api/notifications" in paths
    assert "/api/health/sources" in paths
    assert "/api/export/jobs.csv" in paths
    assert "/api/export/applications.csv" in paths
    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )
    assert "http://localhost:5173" in cors.kwargs["allow_origins"]
    assert "localhost" in cors.kwargs["allow_origin_regex"]
    app.state.run_manager.shutdown()


def endpoint(app, path: str, method: str):
    return next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == path
        and method in getattr(route, "methods", set())
    )


def test_application_stage_history_tasks_and_analytics(tmp_path: Path) -> None:
    app = make_app(tmp_path, {"fixture": ApiFixtureScraper})
    with app.state.session_factory() as session:
        job = Job(
            fingerprint="a" * 64,
            canonical_url="https://example.com/tracked-job",
            title="Tracked Engineer",
            company="Example",
            location="Paris",
        )
        session.add(job)
        session.commit()

        create = endpoint(app, "/api/applications", "POST")
        update = endpoint(app, "/api/applications/{application_id}", "PATCH")
        create_task = endpoint(
            app, "/api/applications/{application_id}/tasks", "POST"
        )
        analytics = endpoint(app, "/api/analytics/overview", "GET")

        application = create(ApplicationCreate(job_id=job.id), session)
        changed = update(
            application.id, ApplicationUpdate(stage="applied"), session
        )
        create_task(
            application.id,
            TaskCreate(
                title="Follow up",
                due_at=datetime.now(timezone.utc) - timedelta(days=1),
            ),
            session,
        )
        overview = analytics(session)

        assert changed.stage == "applied"
        assert [event.event_type for event in changed.events] == [
            "created",
            "stage_changed",
        ]
        assert overview.total_applications == 1
        assert overview.stage_counts == {"applied": 1}
        assert overview.overdue_tasks == 1
    app.state.run_manager.shutdown()


def test_background_search_persists_jobs_and_events(tmp_path: Path) -> None:
    app = make_app(tmp_path, {"fixture": ApiFixtureScraper})
    manager = app.state.run_manager
    run_id = manager.start(SearchCriteria(keywords=["python"]), ["all"], False)
    search_run = wait_for_terminal(app, run_id)

    assert search_run.status == "completed"
    assert search_run.total_jobs == 1
    with app.state.session_factory() as session:
        job = session.scalar(select(Job))
        assert job is not None
        assert job.title == "Python API Engineer"
        assert job.remote is True

    events = list(manager.events(run_id))
    assert events[-1]["type"] == "search_completed"
    assert any(event["type"] == "job_found" for event in events)
    manager.shutdown()


def test_running_search_can_be_cancelled(tmp_path: Path) -> None:
    app = make_app(tmp_path, {"slow": SlowFixtureScraper})
    manager = app.state.run_manager
    run_id = manager.start(SearchCriteria(), ["slow"], False)
    assert manager.cancel(run_id) is True

    search_run = wait_for_terminal(app, run_id)
    assert search_run.status == "cancelled"
    assert search_run.total_jobs < 30
    manager.shutdown()


def test_saved_search_scheduler_dispatches_and_notifies(tmp_path: Path) -> None:
    app = make_app(tmp_path, {"fixture": ApiFixtureScraper})
    create = endpoint(app, "/api/saved-searches", "POST")
    with app.state.session_factory() as session:
        saved = create(
            SavedSearchCreate(
                name="Daily Python",
                criteria=SearchCriteria(keywords=["python"], location="Paris"),
                sources=["fixture"],
                schedule_enabled=True,
                schedule_interval_minutes=60,
            ),
            session,
        )
        record = session.get(Search, saved.id)
        record.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()

    run_ids = app.state.scheduler.run_due()
    assert len(run_ids) == 1
    assert wait_for_terminal(app, run_ids[0]).status == "completed"

    with app.state.session_factory() as session:
        refreshed = session.get(Search, saved.id)
        notifications = session.scalars(
            select(Notification).order_by(Notification.created_at)
        ).all()
        assert refreshed.last_run_at is not None
        assert refreshed.next_run_at is not None
        assert {item.kind for item in notifications} == {
            "scheduled_search",
            "search_complete",
        }
    app.state.run_manager.shutdown()
