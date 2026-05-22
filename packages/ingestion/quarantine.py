"""Écriture des lignes CSV rejetées."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path


class QuarantineWriter:
    def __init__(self, directory: Path, source_name: str) -> None:
        self._directory = directory
        self._source_name = source_name
        self._path: Path | None = None
        self._handle = None
        self._writer: csv.writer | None = None

    @property
    def path(self) -> Path | None:
        return self._path

    def write(self, line_number: int, raw_value: str, reason: str) -> None:
        if self._writer is None:
            self._directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            safe_source = self._source_name.replace("/", "_")
            self._path = self._directory / f"{stamp}_{safe_source}.quarantine.csv"
            self._handle = self._path.open("w", encoding="utf-8", newline="")
            self._writer = csv.writer(self._handle)
            self._writer.writerow(["line_number", "raw_value", "reason", "source_file"])
        assert self._writer is not None
        self._writer.writerow([line_number, raw_value, reason, self._source_name])

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
