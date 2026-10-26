"""Tests for the presentation-independent search orchestration."""

from typing import Iterator, List, Optional

from jobscraper.models.job import JobOffer, SearchCriteria
from jobscraper.scrapers.base import BaseScraper
from jobscraper.services.search import (
    SearchEvent,
    SearchEventType,
    SearchService,
    SourceRunStatus,
)


def make_job(source: str, suffix: str) -> JobOffer:
    return JobOffer(
        id=f"{source}_{suffix}",
        source=source,
        url=f"https://example.com/{source}/{suffix}",
        title=f"Job {suffix}",
        company="Example",
        location="Paris",
    )


class SuccessfulScraper(BaseScraper):
    name = "successful"

    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        yield make_job(self.name, "1")
        yield make_job(self.name, "2")

    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        return None


class FailingScraper(BaseScraper):
    name = "failing"

    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        raise RuntimeError("source unavailable")
        yield  # pragma: no cover - keeps this method an iterator

    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        return None


class PartiallyFailingScraper(BaseScraper):
    name = "partial"

    def search(self, criteria: SearchCriteria) -> Iterator[JobOffer]:
        yield make_job(self.name, "1")
        raise RuntimeError("failed after first result")

    def get_job_details(self, job_id: str) -> Optional[JobOffer]:
        return None


def test_search_collects_jobs_and_emits_progress() -> None:
    events: List[SearchEvent] = []
    service = SearchService(
        scraper_factories={"successful": SuccessfulScraper}
    )

    result = service.search(SearchCriteria(), on_event=events.append)

    assert [job.id for job in result.jobs] == ["successful_1", "successful_2"]
    assert result.sources["successful"].status == SourceRunStatus.COMPLETED
    assert result.sources["successful"].job_count == 2
    assert [event.type for event in events] == [
        SearchEventType.SOURCE_STARTED,
        SearchEventType.JOB_FOUND,
        SearchEventType.JOB_FOUND,
        SearchEventType.SOURCE_COMPLETED,
        SearchEventType.SEARCH_COMPLETED,
    ]


def test_source_failure_does_not_discard_other_source_results() -> None:
    service = SearchService(
        scraper_factories={
            "failing": FailingScraper,
            "successful": SuccessfulScraper,
        }
    )

    result = service.search(SearchCriteria())

    assert len(result.jobs) == 2
    assert result.sources["failing"].status == SourceRunStatus.FAILED
    assert result.sources["failing"].error == "source unavailable"
    assert result.sources["successful"].status == SourceRunStatus.COMPLETED


def test_results_emitted_before_a_source_failure_are_preserved() -> None:
    service = SearchService(
        scraper_factories={"partial": PartiallyFailingScraper}
    )

    result = service.search(SearchCriteria())

    assert [job.id for job in result.jobs] == ["partial_1"]
    assert result.sources["partial"].job_count == 1
    assert result.sources["partial"].status == SourceRunStatus.FAILED


def test_all_uses_each_registered_source_once() -> None:
    service = SearchService(
        scraper_factories={"successful": SuccessfulScraper}
    )

    result = service.search(SearchCriteria(), sources=["all", "successful"])

    assert len(result.jobs) == 2
    assert list(result.sources) == ["successful"]


def test_unknown_source_is_reported_as_skipped() -> None:
    service = SearchService(
        scraper_factories={"successful": SuccessfulScraper}
    )

    result = service.search(SearchCriteria(), sources=["unknown"])

    assert result.jobs == []
    assert result.sources["unknown"].status == SourceRunStatus.SKIPPED
    assert result.errors == {"unknown": "Unknown source"}
