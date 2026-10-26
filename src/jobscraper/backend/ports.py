"""Ports owned by the backend and implemented by the scraper application."""

from typing import Iterable, List, Optional, Protocol

from jobscraper.models.job import SearchCriteria
from jobscraper.services.search import (
    CancellationCheck,
    ProgressCallback,
    SearchResult,
)


class ScraperGateway(Protocol):
    """Explicit backend-to-scraper application contract."""

    def available_sources(self) -> List[str]:
        ...

    def resolve_sources(self, sources: Optional[Iterable[str]]) -> List[str]:
        ...

    def search(
        self,
        criteria: SearchCriteria,
        sources: Optional[Iterable[str]] = None,
        include_details: bool = False,
        on_event: Optional[ProgressCallback] = None,
        should_cancel: Optional[CancellationCheck] = None,
    ) -> SearchResult:
        ...
