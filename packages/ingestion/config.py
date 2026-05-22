"""Configuration MS-01 — chemins données."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


@dataclass(frozen=True)
class IngestionConfig:
    quarantine_dir: Path

    @classmethod
    def from_env(cls) -> IngestionConfig:
        root = find_repo_root()
        custom = os.environ.get("INGESTION_QUARANTINE_DIR", "").strip()
        quarantine = Path(custom) if custom else root / "data" / "quarantine"
        return cls(quarantine_dir=quarantine)


def get_ingestion_config() -> IngestionConfig:
    return IngestionConfig.from_env()
