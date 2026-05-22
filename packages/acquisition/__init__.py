"""MS-02 — Acquisition / scraping (download + validate + handoff MS-03)."""

from packages.acquisition.fetch import fetch
from packages.acquisition.models import (
    FetchJob,
    FetchResult,
    ValidationAction,
    ValidationDecision,
)
from packages.acquisition.sources import (
    BnbAdapter,
    KboAdapter,
    MoniteurAdapter,
    StatutesAdapter,
    default_adapters,
    get_adapters,
)
from packages.acquisition.validate import validate_fetch
from packages.acquisition.worker import scrape_batch

__all__ = [
    "BnbAdapter",
    "FetchJob",
    "FetchResult",
    "KboAdapter",
    "MoniteurAdapter",
    "StatutesAdapter",
    "ValidationAction",
    "ValidationDecision",
    "default_adapters",
    "fetch",
    "get_adapters",
    "scrape_batch",
    "validate_fetch",
]
