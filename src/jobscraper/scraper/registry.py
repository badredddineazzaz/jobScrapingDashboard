"""Factory and registry for concrete scraper adapters."""

import os
from typing import Callable, Dict, Mapping

from jobscraper.config import Config
from jobscraper.scrapers.adzuna import AdzunaScraper
from jobscraper.scrapers.base import BaseScraper
from jobscraper.scrapers.francetravail import FranceTravailScraper
from jobscraper.scrapers.hellowork import HelloWorkScraper
from jobscraper.scrapers.linkedin import LinkedInScraper
from jobscraper.scrapers.wttj import WTTJScraper

ScraperFactory = Callable[[], BaseScraper]


class ScraperRegistry:
    """Immutable-by-convention source registry exposed to the backend."""

    def __init__(self, factories: Mapping[str, ScraperFactory]) -> None:
        self._factories = dict(factories)

    def factories(self) -> Dict[str, ScraperFactory]:
        """Return a copy so callers cannot mutate the registry accidentally."""

        return dict(self._factories)


def default_scraper_registry(config: Config) -> ScraperRegistry:
    """Build the production registry from application configuration."""

    factories: Dict[str, ScraperFactory] = {}
    if config.linkedin.enabled:
        factories["linkedin"] = lambda: LinkedInScraper(
            {"delay": config.linkedin.delay_between_requests}
        )
    if config.hellowork.enabled:
        factories["hellowork"] = lambda: HelloWorkScraper(
            {"delay": config.hellowork.delay_between_requests}
        )
    if config.francetravail.enabled:
        factories["francetravail"] = lambda: FranceTravailScraper(
            {"delay": config.francetravail.delay_between_requests}
        )
    factories["adzuna"] = lambda: AdzunaScraper(
        {
            "app_id": os.getenv("ADZUNA_APP_ID"),
            "app_key": os.getenv("ADZUNA_APP_KEY"),
        }
    )
    if config.wttj.enabled:
        factories["wttj"] = lambda: WTTJScraper(
            {"delay": config.wttj.delay_between_requests}
        )
    return ScraperRegistry(factories)
