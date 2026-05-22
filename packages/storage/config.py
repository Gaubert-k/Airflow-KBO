"""Configuration MS-03 (variables d'environnement)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is not None and value.strip():
        return value.strip()
    return default


@dataclass(frozen=True)
class StorageConfig:
    """Paramètres du stockage brut."""

    hdfs_raw_root: str
    hdfs_local_root: Path
    sidecar_schema_version: int = 1
    metadata_filename: str = "metadata.json"
    default_document_name: str = "document.html"

    @classmethod
    def from_env(cls) -> StorageConfig:
        raw_root = _env("HDFS_RAW_ROOT", "hdfs://localhost:9000/raw/v1")
        if raw_root is None:
            msg = "HDFS_RAW_ROOT must be set"
            raise ValueError(msg)
        local = _env("HDFS_LOCAL_ROOT")
        if local is None:
            local = str(Path.cwd() / "data" / "hdfs-stub")
        return cls(
            hdfs_raw_root=raw_root.rstrip("/"),
            hdfs_local_root=Path(local),
        )


def get_storage_config() -> StorageConfig:
    return StorageConfig.from_env()
