"""Modèles de sortie MS-04 (versionnés)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedDocument:
    enterprise_number: str
    source: str
    doc_type: str
    extractor_version: str
    schema_version: int
    partial: bool
    fields: dict[str, Any]
    discovery_candidates: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    ok: bool
    reason_code: str
    document: ParsedDocument | None = None
