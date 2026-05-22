"""MS-04 — Extraction HTML → données structurées."""

from packages.extraction.models import ParseResult, ParsedDocument
from packages.extraction.parse import parse_raw_document
from packages.extraction.worker import parse_batch

__all__ = [
    "ParseResult",
    "ParsedDocument",
    "parse_batch",
    "parse_raw_document",
]
