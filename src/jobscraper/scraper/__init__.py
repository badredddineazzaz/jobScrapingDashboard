"""Scraper application boundary.

Concrete source adapters live in :mod:`jobscraper.scrapers`; this package
owns their registry and exposes the composition point used by the backend.
"""

from jobscraper.scraper.registry import ScraperRegistry, default_scraper_registry

__all__ = ["ScraperRegistry", "default_scraper_registry"]
