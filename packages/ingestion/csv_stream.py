"""Lecture CSV en flux — délimiteur, encodage, colonne entreprise."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_ENTERPRISE_COLUMN_ALIASES = (
    "enterprise_number",
    "enterprisenumber",
    "entitynumber",
    "numero",
    "ondernemingsnummer",
    "bce",
    "n°",
    "nº",
    "no",
    "numéro",
)


@dataclass(frozen=True)
class CsvStreamConfig:
    path: Path
    delimiter: str
    encoding: str
    column_index: int
    has_header: bool


def detect_encoding(path: Path) -> str:
    """UTF-8 par défaut ; latin-1 si UTF-8 échoue sur un échantillon."""
    sample = path.read_bytes()[:65536]
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return "latin-1"
    return "utf-8"


def detect_delimiter(path: Path, encoding: str) -> str:
    with path.open("r", encoding=encoding, newline="") as handle:
        first = handle.readline()
    if not first:
        return ","
    commas = first.count(",")
    semicolons = first.count(";")
    return ";" if semicolons > commas else ","


def _normalize_header_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def resolve_column_index(
    header: list[str] | None,
    *,
    explicit_column: str | None,
) -> int:
    if explicit_column is not None:
        if header is None:
            msg = f"Column {explicit_column!r} requested but CSV has no header row"
            raise ValueError(msg)
        normalized = [_normalize_header_name(h) for h in header]
        target = _normalize_header_name(explicit_column)
        try:
            return normalized.index(target)
        except ValueError as exc:
            msg = f"Column {explicit_column!r} not found in header {header!r}"
            raise ValueError(msg) from exc

    if header is not None:
        normalized = [_normalize_header_name(h) for h in header]
        for alias in _ENTERPRISE_COLUMN_ALIASES:
            if alias in normalized:
                return normalized.index(alias)

    return 0


def _header_matches_enterprise_column(header: list[str]) -> bool:
    normalized = {_normalize_header_name(h) for h in header}
    return any(alias in normalized for alias in _ENTERPRISE_COLUMN_ALIASES)


def csv_has_enterprise_column(path: Path, *, column: str | None = None) -> bool:
    """True si le CSV expose une colonne entreprise (sinon à ne pas ingérer, ex. meta/code)."""
    if column is not None:
        return True
    encoding = detect_encoding(path)
    delimiter = detect_delimiter(path, encoding)
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        first_row = next(reader, None)
    if not first_row:
        return False
    return _header_matches_enterprise_column(first_row)


def open_csv_stream(
    path: Path,
    *,
    column: str | None = None,
) -> CsvStreamConfig:
    encoding = detect_encoding(path)
    delimiter = detect_delimiter(path, encoding)
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        first_row = next(reader, None)

    if first_row is None:
        return CsvStreamConfig(
            path=path,
            delimiter=delimiter,
            encoding=encoding,
            column_index=0,
            has_header=False,
        )

    has_header = _header_matches_enterprise_column(first_row)
    if column is not None:
        has_header = True

    if has_header:
        column_index = resolve_column_index(first_row, explicit_column=column)
    else:
        column_index = resolve_column_index(None, explicit_column=column)

    return CsvStreamConfig(
        path=path,
        delimiter=delimiter,
        encoding=encoding,
        column_index=column_index,
        has_header=has_header,
    )


def iter_enterprise_values(
    stream: CsvStreamConfig,
) -> Iterator[tuple[int, str]]:
    """Yield (line_number, raw_cell_value) pour chaque ligne de données."""
    with stream.path.open("r", encoding=stream.encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=stream.delimiter)
        first = next(reader, None)
        if first is None:
            return

        if stream.has_header:
            line_no = 1
        else:
            if stream.column_index < len(first):
                yield 1, first[stream.column_index]
            line_no = 1

        for row in reader:
            line_no += 1
            if stream.column_index >= len(row):
                yield line_no, ""
                continue
            yield line_no, row[stream.column_index]
