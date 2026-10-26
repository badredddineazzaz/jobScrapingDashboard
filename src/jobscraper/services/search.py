"""Reusable orchestration for multi-source job searches.

This module intentionally has no Click or Rich dependencies.  The CLI can render
events today and a background web worker can publish the same events later.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Iterable, List, Mapping, Optional

from loguru import logger

from jobscraper.config import Config, get_config
from jobscraper.models.job import JobOffer, SearchCriteria
from jobscraper.scrapers.base import BaseScraper


DEFAULT_SOURCES = (
    "linkedin",
    "hellowork",
    "francetravail",
    "adzuna",
    "wttj",
)


class SourceRunStatus(str, Enum):
    """Terminal and transient states of one source in a search run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class SearchEventType(str, Enum):
    """Events emitted while a search is running."""

    SOURCE_STARTED = "source_started"
    JOB_FOUND = "job_found"
    SOURCE_COMPLETED = "source_completed"
    SOURCE_FAILED = "source_failed"
    SEARCH_COMPLETED = "search_completed"
    SEARCH_CANCELLED = "search_cancelled"


@dataclass(frozen=True)
class SearchEvent:
    """A UI-neutral progress event."""

    type: SearchEventType
    source: Optional[str] = None
    source_job_count: int = 0
    total_job_count: int = 0
    job: Optional[JobOffer] = None
    error: Optional[str] = None


@dataclass
class SourceRunResult:
    """Outcome for one source."""

    source: str
    status: SourceRunStatus = SourceRunStatus.PENDING
    job_count: int = 0
    error: Optional[str] = None


@dataclass
class SearchResult:
    """Complete result returned by :class:`SearchService`."""

    jobs: List[JobOffer] = field(default_factory=list)
    sources: Dict[str, SourceRunResult] = field(default_factory=dict)
    cancelled: bool = False

    @property
    def errors(self) -> Dict[str, str]:
        """Return source errors without forcing callers to inspect every state."""

        return {
            source: result.error
            for source, result in self.sources.items()
            if result.error is not None
        }


ScraperFactory = Callable[[], BaseScraper]
ProgressCallback = Callable[[SearchEvent], None]
CancellationCheck = Callable[[], bool]


class SearchService:
    """Run searches across scrapers without depending on a presentation layer."""

    def __init__(
        self,
        config: Optional[Config] = None,
        scraper_factories: Optional[Mapping[str, ScraperFactory]] = None,
    ) -> None:
        self.config = config or get_config()
        self.scraper_factories = dict(
            scraper_factories or self._default_scraper_factories()
        )

    def available_sources(self) -> List[str]:
        """Return registered source names in deterministic order."""

        return list(self.scraper_factories.keys())

    def search(
        self,
        criteria: SearchCriteria,
        sources: Optional[Iterable[str]] = None,
        include_details: bool = False,
        on_event: Optional[ProgressCallback] = None,
        should_cancel: Optional[CancellationCheck] = None,
    ) -> SearchResult:
        """Search selected sources, keeping failures isolated per source."""

        selected_sources = self.resolve_sources(sources)
        result = SearchResult(
            sources={name: SourceRunResult(source=name) for name in selected_sources}
        )

        for source in selected_sources:
            if should_cancel is not None and should_cancel():
                return self._cancel(result, on_event)
            source_result = result.sources[source]
            factory = self.scraper_factories.get(source)
            if factory is None:
                source_result.status = SourceRunStatus.SKIPPED
                source_result.error = "Unknown source"
                self._emit(
                    on_event,
                    SearchEvent(
                        type=SearchEventType.SOURCE_FAILED,
                        source=source,
                        total_job_count=len(result.jobs),
                        error=source_result.error,
                    ),
                )
                continue

            source_result.status = SourceRunStatus.RUNNING
            self._emit(
                on_event,
                SearchEvent(
                    type=SearchEventType.SOURCE_STARTED,
                    source=source,
                    total_job_count=len(result.jobs),
                ),
            )

            try:
                with factory() as scraper:
                    for job in scraper.search(criteria):
                        if should_cancel is not None and should_cancel():
                            source_result.status = SourceRunStatus.CANCELLED
                            return self._cancel(result, on_event)
                        if include_details and source == "linkedin":
                            job = self._enrich_linkedin_job(scraper, job)
                        result.jobs.append(job)
                        source_result.job_count += 1
                        self._emit(
                            on_event,
                            SearchEvent(
                                type=SearchEventType.JOB_FOUND,
                                source=source,
                                source_job_count=source_result.job_count,
                                total_job_count=len(result.jobs),
                                job=job,
                            ),
                        )

                source_result.status = SourceRunStatus.COMPLETED
                self._emit(
                    on_event,
                    SearchEvent(
                        type=SearchEventType.SOURCE_COMPLETED,
                        source=source,
                        source_job_count=source_result.job_count,
                        total_job_count=len(result.jobs),
                    ),
                )
            except Exception as exc:
                source_result.status = SourceRunStatus.FAILED
                source_result.error = str(exc)
                logger.exception("Search source {} failed", source)
                self._emit(
                    on_event,
                    SearchEvent(
                        type=SearchEventType.SOURCE_FAILED,
                        source=source,
                        source_job_count=source_result.job_count,
                        total_job_count=len(result.jobs),
                        error=source_result.error,
                    ),
                )

        self._emit(
            on_event,
            SearchEvent(
                type=SearchEventType.SEARCH_COMPLETED,
                total_job_count=len(result.jobs),
            ),
        )
        return result

    @staticmethod
    def _cancel(
        result: SearchResult, callback: Optional[ProgressCallback]
    ) -> SearchResult:
        result.cancelled = True
        for source_result in result.sources.values():
            if source_result.status in {
                SourceRunStatus.PENDING,
                SourceRunStatus.RUNNING,
            }:
                source_result.status = SourceRunStatus.CANCELLED
        SearchService._emit(
            callback,
            SearchEvent(
                type=SearchEventType.SEARCH_CANCELLED,
                total_job_count=len(result.jobs),
            ),
        )
        return result

    def resolve_sources(self, sources: Optional[Iterable[str]]) -> List[str]:
        """Expand ``all`` and remove duplicate source names."""

        requested = list(sources or self.scraper_factories.keys())
        if "all" in requested:
            requested = list(self.scraper_factories.keys())

        # Preserve user/registry order while preventing a source from running twice.
        return list(dict.fromkeys(requested))

    def _default_scraper_factories(self) -> Mapping[str, ScraperFactory]:
        # The local import keeps concrete scraper construction in the scraper
        # application's composition root rather than in backend orchestration.
        from jobscraper.scraper.registry import default_scraper_registry

        return default_scraper_registry(self.config).factories()

    @staticmethod
    def _enrich_linkedin_job(
        scraper: BaseScraper, job: JobOffer
    ) -> JobOffer:
        external_id = job.id.replace("linkedin_", "", 1)
        return scraper.get_job_details(external_id) or job

    @staticmethod
    def _emit(
        callback: Optional[ProgressCallback], event: SearchEvent
    ) -> None:
        if callback is not None:
            callback(event)
