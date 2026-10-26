"""Application services shared by the CLI and the future web API."""

from jobscraper.services.search import (
    DEFAULT_SOURCES,
    SearchEvent,
    SearchEventType,
    SearchResult,
    SearchService,
    SourceRunResult,
    SourceRunStatus,
)
from jobscraper.services.persistence import PersistentSearchRunner

__all__ = [
    "DEFAULT_SOURCES",
    "SearchEvent",
    "SearchEventType",
    "SearchResult",
    "SearchService",
    "PersistentSearchRunner",
    "SourceRunResult",
    "SourceRunStatus",
]
