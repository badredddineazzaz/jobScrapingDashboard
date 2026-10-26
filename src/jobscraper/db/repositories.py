"""Repository layer for jobs and search runs."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobscraper.db.deduplication import canonicalize_url, job_fingerprint
from jobscraper.db.models import Job, JobSource, SearchRun, SearchRunJob
from jobscraper.models.job import JobOffer


def enum_value(value: object) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value))


class JobRepository:
    """Create or update canonical jobs and their source records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, offer: JobOffer) -> Job:
        now = datetime.now(timezone.utc)
        canonical_url = canonicalize_url(str(offer.url))
        fingerprint = job_fingerprint(offer)

        source_record = self.session.scalar(
            select(JobSource).where(
                JobSource.source == offer.source,
                JobSource.external_id == offer.id,
            )
        )
        job = source_record.job if source_record is not None else None

        if job is None:
            job = self.session.scalar(
                select(Job).where(Job.canonical_url == canonical_url)
            )
        if job is None:
            job = self.session.scalar(
                select(Job).where(Job.fingerprint == fingerprint)
            )

        if job is None:
            job = Job(
                fingerprint=fingerprint,
                canonical_url=canonical_url,
                title=offer.title,
                company=offer.company,
                location=offer.location,
            )
            self.session.add(job)
            self.session.flush()

        self._merge_offer(job, offer, now)

        if source_record is None:
            source_record = JobSource(
                job_id=job.id,
                source=offer.source,
                external_id=offer.id,
                url=str(offer.url),
                raw_data=offer.model_dump(mode="json"),
                scraped_at=offer.scraped_at,
                last_seen_at=now,
            )
            self.session.add(source_record)
        else:
            source_record.url = str(offer.url)
            source_record.raw_data = offer.model_dump(mode="json")
            source_record.scraped_at = offer.scraped_at
            source_record.last_seen_at = now

        self.session.flush()
        return job

    @staticmethod
    def _merge_offer(job: Job, offer: JobOffer, now: datetime) -> None:
        job.title = offer.title or job.title
        job.company = offer.company or job.company
        job.location = offer.location or job.location
        job.description = offer.description or job.description
        job.salary_min = (
            offer.salary_min if offer.salary_min is not None else job.salary_min
        )
        job.salary_max = (
            offer.salary_max if offer.salary_max is not None else job.salary_max
        )
        job.salary_currency = offer.salary_currency or job.salary_currency
        job.contract_type = enum_value(offer.contract_type) or job.contract_type
        job.experience_level = (
            enum_value(offer.experience_level) or job.experience_level
        )
        job.remote = offer.remote if offer.remote is not None else job.remote
        job.posted_at = offer.posted_at or job.posted_at
        job.skills = offer.skills or job.skills
        job.benefits = offer.benefits or job.benefits
        job.last_seen_at = now
        job.last_verified_at = now


class SearchRunRepository:
    """Persist run metadata and links to canonical jobs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_job(self, search_run: SearchRun, job: Job) -> None:
        existing = self.session.scalar(
            select(SearchRunJob).where(
                SearchRunJob.search_run_id == search_run.id,
                SearchRunJob.job_id == job.id,
            )
        )
        if existing is None:
            self.session.add(
                SearchRunJob(search_run_id=search_run.id, job_id=job.id)
            )
