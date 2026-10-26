"""FastAPI application factory and HTTP routes."""

import json
import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from jobscraper.api.schemas import (
    JobPage,
    JobRead,
    JobUpdate,
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    AnalyticsOverview,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    SavedSearchCreate,
    SavedSearchRead,
    SavedSearchUpdate,
    NotificationRead,
    SearchRunCreate,
    SearchRunCreated,
    SearchRunRead,
    SourceRunRead,
)
from jobscraper.api.worker import SearchRunManager
from jobscraper.backend.ports import ScraperGateway
from jobscraper.db.database import create_database_engine, create_session_factory
from jobscraper.db.models import (
    Application,
    ApplicationEvent,
    ApplicationTask,
    Base,
    Job,
    JobSource,
    Notification,
    Search,
    SearchRun,
    SearchRunSource,
)
from jobscraper.services.persistence import PersistentSearchRunner
from jobscraper.services.search import SearchService
from jobscraper.services.scheduler import SavedSearchScheduler
from jobscraper.models.job import SearchCriteria


TERMINAL_RUN_STATES = {
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
}


def create_app(
    database_url: Optional[str] = None,
    search_service: Optional[ScraperGateway] = None,
    initialize_schema: bool = False,
) -> FastAPI:
    engine = create_database_engine(database_url)
    if initialize_schema:
        # Intended for isolated tests only. Local and production databases must
        # be created and upgraded through Alembic so revision history is kept.
        Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    service = search_service or SearchService()
    runner = PersistentSearchRunner(service, session_factory)
    manager = SearchRunManager(runner, session_factory)
    scheduler = SavedSearchScheduler(session_factory, manager)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        del application
        scheduler.start()
        yield
        scheduler.stop()
        manager.shutdown()
        engine.dispose()

    app = FastAPI(
        title="JobScraper Dashboard API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.session_factory = session_factory
    app.state.search_service = service
    app.state.run_manager = manager
    app.state.scheduler = scheduler
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Type"],
    )

    def get_session(request: Request) -> Iterator[Session]:
        factory: sessionmaker[Session] = request.app.state.session_factory
        with factory() as session:
            yield session

    @app.get("/api/health")
    def health(session: Session = Depends(get_session)) -> dict:
        session.execute(select(1))
        return {"status": "ok", "database": "ok"}

    @app.get("/api/sources")
    def sources(request: Request) -> dict:
        available = request.app.state.search_service.available_sources()
        return {"items": [{"name": name, "enabled": True} for name in available]}

    @app.get("/api/health/sources")
    def source_health(
        request: Request, session: Session = Depends(get_session)
    ) -> dict:
        items = []
        for source_name in request.app.state.search_service.available_sources():
            latest = session.scalar(
                select(SearchRunSource)
                .where(SearchRunSource.source == source_name)
                .order_by(SearchRunSource.id.desc())
                .limit(1)
            )
            items.append(
                {
                    "name": source_name,
                    "enabled": True,
                    "last_status": latest.status if latest else "not_run",
                    "last_error": latest.error if latest else None,
                }
            )
        return {"items": items}

    @app.post(
        "/api/search-runs",
        response_model=SearchRunCreated,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_search_run(payload: SearchRunCreate, request: Request) -> dict:
        run_id = request.app.state.run_manager.start(
            payload.criteria, payload.sources, payload.include_details
        )
        return {"id": run_id, "status": "running"}

    @app.get("/api/search-runs/{run_id}", response_model=SearchRunRead)
    def get_search_run(
        run_id: str, session: Session = Depends(get_session)
    ) -> SearchRunRead:
        search_run = session.scalar(
            select(SearchRun)
            .options(selectinload(SearchRun.sources))
            .where(SearchRun.id == run_id)
        )
        if search_run is None:
            raise HTTPException(status_code=404, detail="Search run not found")
        return serialize_run(search_run)

    @app.post("/api/search-runs/{run_id}/cancel", response_model=SearchRunCreated)
    def cancel_search_run(
        run_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict:
        search_run = session.get(SearchRun, run_id)
        if search_run is None:
            raise HTTPException(status_code=404, detail="Search run not found")
        if search_run.status in TERMINAL_RUN_STATES:
            raise HTTPException(status_code=409, detail="Search run already finished")
        request.app.state.run_manager.cancel(run_id)
        return {"id": run_id, "status": "cancellation_requested"}

    @app.get("/api/search-runs/{run_id}/events")
    def search_run_events(
        run_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> StreamingResponse:
        if session.get(SearchRun, run_id) is None:
            raise HTTPException(status_code=404, detail="Search run not found")

        def event_stream() -> Iterator[str]:
            for event in request.app.state.run_manager.events(run_id):
                event_type = event.get("type", "message")
                yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/jobs", response_model=JobPage)
    def list_jobs(
        q: Optional[str] = None,
        source: Optional[str] = None,
        company: Optional[str] = None,
        location: Optional[str] = None,
        contract_type: Optional[str] = None,
        remote: Optional[bool] = None,
        sort: str = Query(default="newest", pattern="^(newest|posted|title)$"),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        session: Session = Depends(get_session),
    ) -> JobPage:
        statement = select(Job).options(selectinload(Job.sources))
        count_statement = select(func.count(func.distinct(Job.id)))
        if source:
            statement = statement.join(JobSource)
            count_statement = count_statement.select_from(Job).join(JobSource)
            statement = statement.where(JobSource.source == source)
            count_statement = count_statement.where(JobSource.source == source)
        else:
            count_statement = count_statement.select_from(Job)

        filters = []
        if q:
            term = f"%{q}%"
            filters.append(
                or_(
                    Job.title.ilike(term),
                    Job.company.ilike(term),
                    Job.description.ilike(term),
                )
            )
        if company:
            filters.append(Job.company.ilike(f"%{company}%"))
        if location:
            filters.append(Job.location.ilike(f"%{location}%"))
        if contract_type:
            filters.append(Job.contract_type == contract_type)
        if remote is not None:
            filters.append(Job.remote == remote)
        if filters:
            statement = statement.where(*filters)
            count_statement = count_statement.where(*filters)

        order = {
            "newest": Job.first_seen_at.desc(),
            "posted": Job.posted_at.desc(),
            "title": Job.title.asc(),
        }[sort]
        total = session.scalar(count_statement) or 0
        jobs = session.scalars(
            statement.distinct().order_by(order).limit(limit).offset(offset)
        ).all()
        return JobPage(
            items=[JobRead.model_validate(job) for job in jobs],
            total=total,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/jobs/{job_id}", response_model=JobRead)
    def get_job(job_id: str, session: Session = Depends(get_session)) -> JobRead:
        job = session.scalar(
            select(Job)
            .options(selectinload(Job.sources))
            .where(Job.id == job_id)
        )
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobRead.model_validate(job)

    @app.patch("/api/jobs/{job_id}", response_model=JobRead)
    def update_job(
        job_id: str,
        payload: JobUpdate,
        session: Session = Depends(get_session),
    ) -> JobRead:
        job = session.scalar(
            select(Job)
            .options(selectinload(Job.sources))
            .where(Job.id == job_id)
        )
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(job, field, value)
        session.commit()
        session.refresh(job)
        return JobRead.model_validate(job)

    application_load = (
        selectinload(Application.job).selectinload(Job.sources),
        selectinload(Application.events),
        selectinload(Application.tasks),
    )

    @app.get("/api/applications", response_model=list[ApplicationRead])
    def list_applications(
        stage: Optional[str] = None,
        session: Session = Depends(get_session),
    ) -> list[ApplicationRead]:
        statement = select(Application).options(*application_load)
        if stage:
            statement = statement.where(Application.stage == stage)
        items = session.scalars(
            statement.order_by(Application.updated_at.desc())
        ).all()
        return [ApplicationRead.model_validate(item) for item in items]

    @app.post(
        "/api/applications",
        response_model=ApplicationRead,
        status_code=status.HTTP_201_CREATED,
    )
    def create_application(
        payload: ApplicationCreate,
        session: Session = Depends(get_session),
    ) -> ApplicationRead:
        job = session.get(Job, payload.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        existing = session.scalar(
            select(Application).where(Application.job_id == payload.job_id)
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="Application already exists")
        values = payload.model_dump()
        if payload.stage == "applied" and payload.applied_at is None:
            values["applied_at"] = datetime.now(timezone.utc)
        application = Application(**values)
        session.add(application)
        session.flush()
        session.add(
            ApplicationEvent(
                application_id=application.id,
                event_type="created",
                to_stage=application.stage,
            )
        )
        session.commit()
        return load_application(session, application.id, application_load)

    @app.get("/api/applications/{application_id}", response_model=ApplicationRead)
    def get_application(
        application_id: str,
        session: Session = Depends(get_session),
    ) -> ApplicationRead:
        return load_application(session, application_id, application_load)

    @app.patch("/api/applications/{application_id}", response_model=ApplicationRead)
    def update_application(
        application_id: str,
        payload: ApplicationUpdate,
        session: Session = Depends(get_session),
    ) -> ApplicationRead:
        application = session.get(Application, application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        values = payload.model_dump(exclude_unset=True)
        new_stage = values.get("stage")
        if new_stage is not None and new_stage != application.stage:
            previous_stage = application.stage
            session.add(
                ApplicationEvent(
                    application_id=application.id,
                    event_type="stage_changed",
                    from_stage=previous_stage,
                    to_stage=new_stage,
                )
            )
            if new_stage == "applied" and application.applied_at is None:
                application.applied_at = datetime.now(timezone.utc)
        for field, value in values.items():
            setattr(application, field, value)
        application.updated_at = datetime.now(timezone.utc)
        session.commit()
        return load_application(session, application.id, application_load)

    @app.post(
        "/api/applications/{application_id}/tasks",
        response_model=TaskRead,
        status_code=status.HTTP_201_CREATED,
    )
    def create_task(
        application_id: str,
        payload: TaskCreate,
        session: Session = Depends(get_session),
    ) -> TaskRead:
        if session.get(Application, application_id) is None:
            raise HTTPException(status_code=404, detail="Application not found")
        task = ApplicationTask(application_id=application_id, **payload.model_dump())
        session.add(task)
        session.commit()
        session.refresh(task)
        return TaskRead.model_validate(task)

    @app.patch("/api/tasks/{task_id}", response_model=TaskRead)
    def update_task(
        task_id: str,
        payload: TaskUpdate,
        session: Session = Depends(get_session),
    ) -> TaskRead:
        task = session.get(ApplicationTask, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(task, field, value)
        session.commit()
        session.refresh(task)
        return TaskRead.model_validate(task)

    @app.get("/api/analytics/overview", response_model=AnalyticsOverview)
    def analytics_overview(
        session: Session = Depends(get_session),
    ) -> AnalyticsOverview:
        stage_rows = session.execute(
            select(Application.stage, func.count(Application.id)).group_by(
                Application.stage
            )
        ).all()
        stage_counts = {stage: count for stage, count in stage_rows}
        inactive = {"rejected", "withdrawn", "archived"}
        active = sum(
            count for stage, count in stage_counts.items() if stage not in inactive
        )
        overdue = session.scalar(
            select(func.count(ApplicationTask.id)).where(
                ApplicationTask.completed.is_(False),
                ApplicationTask.due_at < datetime.now(timezone.utc),
            )
        ) or 0
        return AnalyticsOverview(
            total_applications=sum(stage_counts.values()),
            active_applications=active,
            overdue_tasks=overdue,
            stage_counts=stage_counts,
        )

    @app.get("/api/saved-searches", response_model=list[SavedSearchRead])
    def list_saved_searches(
        session: Session = Depends(get_session),
    ) -> list[SavedSearchRead]:
        items = session.scalars(select(Search).order_by(Search.updated_at.desc())).all()
        return [SavedSearchRead.model_validate(item) for item in items]

    @app.post(
        "/api/saved-searches",
        response_model=SavedSearchRead,
        status_code=status.HTTP_201_CREATED,
    )
    def create_saved_search(
        payload: SavedSearchCreate,
        session: Session = Depends(get_session),
    ) -> SavedSearchRead:
        values = payload.model_dump()
        values["criteria"] = payload.criteria.model_dump(mode="json")
        if payload.schedule_enabled:
            interval = payload.schedule_interval_minutes or 1440
            values["schedule_interval_minutes"] = interval
            values["next_run_at"] = datetime.now(timezone.utc) + timedelta(
                minutes=interval
            )
        saved_search = Search(**values)
        session.add(saved_search)
        session.commit()
        session.refresh(saved_search)
        return SavedSearchRead.model_validate(saved_search)

    @app.patch("/api/saved-searches/{search_id}", response_model=SavedSearchRead)
    def update_saved_search(
        search_id: str,
        payload: SavedSearchUpdate,
        session: Session = Depends(get_session),
    ) -> SavedSearchRead:
        saved_search = session.get(Search, search_id)
        if saved_search is None:
            raise HTTPException(status_code=404, detail="Saved search not found")
        values = payload.model_dump(exclude_unset=True)
        if payload.criteria is not None:
            values["criteria"] = payload.criteria.model_dump(mode="json")
        for field, value in values.items():
            setattr(saved_search, field, value)
        if saved_search.schedule_enabled:
            interval = saved_search.schedule_interval_minutes or 1440
            saved_search.schedule_interval_minutes = interval
            saved_search.next_run_at = datetime.now(timezone.utc) + timedelta(
                minutes=interval
            )
        else:
            saved_search.next_run_at = None
        saved_search.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(saved_search)
        return SavedSearchRead.model_validate(saved_search)

    @app.post("/api/saved-searches/{search_id}/run", response_model=SearchRunCreated)
    def run_saved_search(
        search_id: str,
        request: Request,
        session: Session = Depends(get_session),
    ) -> dict:
        saved_search = session.get(Search, search_id)
        if saved_search is None:
            raise HTTPException(status_code=404, detail="Saved search not found")
        run_id = request.app.state.run_manager.start(
            SearchCriteria.model_validate(saved_search.criteria),
            saved_search.sources or ["all"],
            saved_search.include_details,
        )
        saved_search.last_run_at = datetime.now(timezone.utc)
        session.commit()
        return {"id": run_id, "status": "running"}

    @app.delete("/api/saved-searches/{search_id}", status_code=204)
    def delete_saved_search(
        search_id: str, session: Session = Depends(get_session)
    ) -> None:
        saved_search = session.get(Search, search_id)
        if saved_search is None:
            raise HTTPException(status_code=404, detail="Saved search not found")
        session.delete(saved_search)
        session.commit()

    @app.get("/api/notifications", response_model=list[NotificationRead])
    def list_notifications(
        unread_only: bool = False,
        session: Session = Depends(get_session),
    ) -> list[NotificationRead]:
        statement = select(Notification)
        if unread_only:
            statement = statement.where(Notification.read.is_(False))
        items = session.scalars(
            statement.order_by(Notification.created_at.desc()).limit(100)
        ).all()
        return [NotificationRead.model_validate(item) for item in items]

    @app.patch("/api/notifications/{notification_id}/read", response_model=NotificationRead)
    def mark_notification_read(
        notification_id: str,
        session: Session = Depends(get_session),
    ) -> NotificationRead:
        notification = session.get(Notification, notification_id)
        if notification is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        notification.read = True
        session.commit()
        session.refresh(notification)
        return NotificationRead.model_validate(notification)

    @app.get("/api/export/jobs.csv")
    def export_jobs(session: Session = Depends(get_session)) -> StreamingResponse:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["title", "company", "location", "contract", "remote", "url"])
        for job in session.scalars(
            select(Job).options(selectinload(Job.sources)).order_by(Job.first_seen_at.desc())
        ):
            writer.writerow(
                [
                    job.title,
                    job.company,
                    job.location,
                    job.contract_type or "",
                    job.remote,
                    job.sources[0].url if job.sources else job.canonical_url or "",
                ]
            )
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=jobs.csv"},
        )

    @app.get("/api/export/applications.csv")
    def export_applications(
        session: Session = Depends(get_session),
    ) -> StreamingResponse:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "job_title",
                "company",
                "location",
                "stage",
                "applied_at",
                "next_action_at",
                "contact_name",
                "contact_email",
                "notes",
            ]
        )
        applications = session.scalars(
            select(Application)
            .options(selectinload(Application.job))
            .order_by(Application.updated_at.desc())
        )
        for application in applications:
            writer.writerow(
                [
                    application.job.title,
                    application.job.company,
                    application.job.location,
                    application.stage,
                    application.applied_at or "",
                    application.next_action_at or "",
                    application.contact_name or "",
                    application.contact_email or "",
                    application.notes or "",
                ]
            )
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=applications.csv"
            },
        )

    return app


def serialize_run(search_run: SearchRun) -> SearchRunRead:
    return SearchRunRead(
        id=search_run.id,
        status=search_run.status,
        criteria=search_run.criteria,
        total_jobs=search_run.total_jobs,
        error=search_run.error,
        created_at=search_run.created_at,
        started_at=search_run.started_at,
        completed_at=search_run.completed_at,
        sources=[
            SourceRunRead(
                source=item.source,
                status=item.status,
                job_count=item.job_count,
                error=item.error,
            )
            for item in search_run.sources
        ],
    )


def load_application(session: Session, application_id: str, options) -> ApplicationRead:
    application = session.scalar(
        select(Application)
        .options(*options)
        .where(Application.id == application_id)
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationRead.model_validate(application)


app = create_app()
