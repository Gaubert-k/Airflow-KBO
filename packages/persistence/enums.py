"""Énumérations gelées MS-05 (contrat public-interfaces.md)."""

from __future__ import annotations

from enum import StrEnum


class SeedSource(StrEnum):
    CSV = "CSV"
    DISCOVERED = "DISCOVERED"


class ProcessingState(StrEnum):
    NEW = "NEW"
    QUEUED_SCRAPE = "QUEUED_SCRAPE"
    SCRAPING = "SCRAPING"
    RAW_STORED = "RAW_STORED"
    QUEUED_PARSE = "QUEUED_PARSE"
    PARSING = "PARSING"
    STRUCTURED = "STRUCTURED"
    FAILED_SCRAPE = "FAILED_SCRAPE"
    FAILED_PARSE = "FAILED_PARSE"
    FAILED_VALIDATE = "FAILED_VALIDATE"


class RawDocumentStatus(StrEnum):
    """État du registre raw_documents (distinct des états plateforme)."""

    STORED = "STORED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
