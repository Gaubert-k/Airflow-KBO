"""Ingestion de tous les CSV entreprise — une passe pour remplir la base (MS-10)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from packages.ingestion.csv_stream import csv_has_enterprise_column
from packages.ingestion.ingest import ingest_csv
from packages.orchestration.paths import DEFAULT_CSV_DIRS
from packages.orchestration.serializers import ingest_report_to_dict

logger = logging.getLogger(__name__)


def discover_enterprise_csv_files(
    directories: list[str | Path],
    *,
    column: str | None = None,
) -> list[Path]:
    """Liste les ``*.csv`` contenant une colonne entreprise (ignore meta, code, etc.)."""
    found: list[Path] = []
    seen: set[Path] = set()
    for directory in directories:
        root = Path(directory).resolve()
        if not root.is_dir():
            logger.warning("ingest dir missing, skip: %s", root)
            continue
        for path in sorted(root.glob("*.csv")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            if not csv_has_enterprise_column(resolved, column=column):
                logger.info("skip csv without enterprise column: %s", resolved.name)
                continue
            seen.add(resolved)
            found.append(resolved)
    return found


def run_ingest_all_csv(
    csv_dirs: list[str] | None = None,
    *,
    column: str | None = None,
    batch_size: int = 5000,
) -> dict[str, Any]:
    """
    Ingère tous les CSV « entreprise » des répertoires (seed + input par défaut).

    Idempotent : relancer ne recrée pas les numéros déjà en base.
    """
    dirs = [Path(d) for d in (csv_dirs or DEFAULT_CSV_DIRS)]
    files = discover_enterprise_csv_files(dirs, column=column)
    if not files:
        msg = f"No enterprise CSV files under {dirs!r}"
        raise FileNotFoundError(msg)

    per_file: list[dict[str, Any]] = []
    totals = {
        "rows_read": 0,
        "created": 0,
        "already_existed": 0,
        "rejected": 0,
        "duration_seconds": 0.0,
    }

    for path in files:
        report = ingest_csv(path, column=column, batch_size=batch_size)
        summary = ingest_report_to_dict(report)
        per_file.append(summary)
        for key in ("rows_read", "created", "already_existed", "rejected", "duration_seconds"):
            totals[key] += summary[key]

    return {
        "mode": "ingest_all",
        "directories": [str(d) for d in dirs],
        "files_processed": len(per_file),
        "files": per_file,
        **totals,
    }
