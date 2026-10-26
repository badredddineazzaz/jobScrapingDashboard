"""Conservative helpers for identifying the same job across sources."""

import hashlib
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from jobscraper.models.job import JobOffer


def normalize_text(value: str) -> str:
    """Normalize display text for equality checks without fuzzy guessing."""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def canonicalize_url(url: str) -> str:
    """Remove query parameters and fragments commonly used for tracking."""

    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, "", ""))


def job_fingerprint(job: JobOffer) -> str:
    """Hash stable identity fields for conservative cross-source matching."""

    identity = "|".join(
        (
            normalize_text(job.title),
            normalize_text(job.company),
            normalize_text(job.location),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
