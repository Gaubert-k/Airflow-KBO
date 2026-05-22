"""Rapport d'ingestion CSV (contrat gelé MS-01)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IngestReport:
    rows_read: int
    created: int
    already_existed: int
    rejected: int
    quarantine_path: Path | None
    source_file: Path
    duration_seconds: float
