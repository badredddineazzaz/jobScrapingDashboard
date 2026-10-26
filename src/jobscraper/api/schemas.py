"""Public API request and response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from jobscraper.models.job import SearchCriteria


class SearchRunCreate(BaseModel):
    criteria: SearchCriteria
    sources: List[str] = Field(default_factory=lambda: ["all"])
    include_details: bool = False


class SearchRunCreated(BaseModel):
    id: str
    status: str


class SourceRunRead(BaseModel):
    source: str
    status: str
    job_count: int
    error: Optional[str]


class SearchRunRead(BaseModel):
    id: str
    status: str
    criteria: Dict[str, Any]
    total_jobs: int
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    sources: List[SourceRunRead]


class JobSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    external_id: str
    url: str
    scraped_at: datetime
    last_seen_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    company: str
    location: str
    description: Optional[str]
    canonical_url: Optional[str]
    salary_min: Optional[float]
    salary_max: Optional[float]
    salary_currency: str
    contract_type: Optional[str]
    experience_level: Optional[str]
    remote: Optional[bool]
    posted_at: Optional[datetime]
    skills: List[str]
    benefits: List[str]
    first_seen_at: datetime
    last_seen_at: datetime
    saved: bool
    hidden: bool
    user_notes: Optional[str]
    user_tags: List[str]
    sources: List[JobSourceRead] = Field(default_factory=list)


class JobPage(BaseModel):
    items: List[JobRead]
    total: int
    limit: int
    offset: int


class JobUpdate(BaseModel):
    saved: Optional[bool] = None
    hidden: Optional[bool] = None
    user_notes: Optional[str] = None
    user_tags: Optional[List[str]] = None


ApplicationStage = Literal[
    "saved",
    "preparing",
    "applied",
    "screening",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
    "archived",
]


class ApplicationCreate(BaseModel):
    job_id: str
    stage: ApplicationStage = "saved"
    applied_at: Optional[datetime] = None
    next_action_at: Optional[datetime] = None
    salary_expectation: Optional[float] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


class ApplicationUpdate(BaseModel):
    stage: Optional[ApplicationStage] = None
    applied_at: Optional[datetime] = None
    next_action_at: Optional[datetime] = None
    salary_expectation: Optional[float] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


class ApplicationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    from_stage: Optional[str]
    to_stage: Optional[str]
    note: Optional[str]
    created_at: datetime


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    due_at: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    due_at: Optional[datetime] = None
    completed: Optional[bool] = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    due_at: Optional[datetime]
    completed: bool
    created_at: datetime


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stage: str
    applied_at: Optional[datetime]
    next_action_at: Optional[datetime]
    salary_expectation: Optional[float]
    contact_name: Optional[str]
    contact_email: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    job: JobRead
    events: List[ApplicationEventRead]
    tasks: List[TaskRead]


class AnalyticsOverview(BaseModel):
    total_applications: int
    active_applications: int
    overdue_tasks: int
    stage_counts: Dict[str, int]


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    criteria: SearchCriteria
    sources: List[str] = Field(default_factory=lambda: ["all"])
    include_details: bool = False
    schedule_enabled: bool = False
    schedule_interval_minutes: Optional[int] = Field(default=None, ge=15)


class SavedSearchUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    criteria: Optional[SearchCriteria] = None
    sources: Optional[List[str]] = None
    include_details: Optional[bool] = None
    schedule_enabled: Optional[bool] = None
    schedule_interval_minutes: Optional[int] = Field(default=None, ge=15)


class SavedSearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: Optional[str]
    criteria: Dict[str, Any]
    sources: List[str]
    include_details: bool
    schedule_enabled: bool
    schedule_interval_minutes: Optional[int]
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    title: str
    message: str
    read: bool
    entity_type: Optional[str]
    entity_id: Optional[str]
    created_at: datetime
