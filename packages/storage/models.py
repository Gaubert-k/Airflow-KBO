"""Modèles de données MS-03."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PutResult:
    hdfs_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class StoreResult:
    hdfs_dir: str
    document_path: str
    metadata_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class RawDocumentStoredEvent:
    """Événement consommable par MS-05 (insert_raw_document_record)."""

    enterprise_number: str
    source: str
    doc_type: str
    run_id: str
    hdfs_dir: str
    document_path: str
    metadata_path: str
    sha256: str
    size_bytes: int
    scraped_at: datetime
    http_status: int
    download_status: str
