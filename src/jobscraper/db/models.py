"""SQLAlchemy models for jobs and search history."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    canonical_url: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    company: Mapped[str] = mapped_column(String(300), index=True)
    location: Mapped[str] = mapped_column(String(300), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    salary_min: Mapped[Optional[float]] = mapped_column(Float)
    salary_max: Mapped[Optional[float]] = mapped_column(Float)
    salary_currency: Mapped[str] = mapped_column(String(10), default="EUR")
    contract_type: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    experience_level: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    remote: Mapped[Optional[bool]]
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    skills: Mapped[List[str]] = mapped_column(JSON, default=list)
    benefits: Mapped[List[str]] = mapped_column(JSON, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    user_notes: Mapped[Optional[str]] = mapped_column(Text)
    user_tags: Mapped[List[str]] = mapped_column(JSON, default=list)

    sources: Mapped[List["JobSource"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    application: Mapped[Optional["Application"]] = relationship(
        back_populates="job", uselist=False
    )


class JobSource(Base):
    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_job_source_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(50), index=True)
    external_id: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    raw_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    job: Mapped[Job] = relationship(back_populates="sources")


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[Optional[str]] = mapped_column(String(200))
    criteria: Mapped[Dict[str, Any]] = mapped_column(JSON)
    sources: Mapped[List[str]] = mapped_column(JSON, default=list)
    include_details: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    schedule_interval_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class SearchRun(Base):
    __tablename__ = "search_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    search_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("searches.id", ondelete="SET NULL")
    )
    criteria: Mapped[Dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    sources: Mapped[List["SearchRunSource"]] = relationship(
        cascade="all, delete-orphan"
    )


class SearchRunSource(Base):
    __tablename__ = "search_run_sources"
    __table_args__ = (
        UniqueConstraint("search_run_id", "source", name="uq_run_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_run_id: Mapped[str] = mapped_column(
        ForeignKey("search_runs.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    job_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class SearchRunJob(Base):
    __tablename__ = "search_run_jobs"
    __table_args__ = (
        UniqueConstraint("search_run_id", "job_id", name="uq_run_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_run_id: Mapped[str] = mapped_column(
        ForeignKey("search_runs.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, index=True
    )
    stage: Mapped[str] = mapped_column(String(30), default="saved", index=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_action_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    salary_expectation: Mapped[Optional[float]] = mapped_column(Float)
    contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    contact_email: Mapped[Optional[str]] = mapped_column(String(320))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    job: Mapped[Job] = relationship(back_populates="application")
    events: Mapped[List["ApplicationEvent"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationEvent.created_at",
    )
    tasks: Mapped[List["ApplicationTask"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(50))
    from_stage: Mapped[Optional[str]] = mapped_column(String(30))
    to_stage: Mapped[Optional[str]] = mapped_column(String(30))
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    application: Mapped[Application] = relationship(back_populates="events")


class ApplicationTask(Base):
    __tablename__ = "application_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    application: Mapped[Application] = relationship(back_populates="tasks")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_id: Mapped[Optional[str]] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
