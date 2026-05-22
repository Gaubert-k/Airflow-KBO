"""Configuration MS-05 — DATABASE_URL."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PersistenceConfig:
    database_url: str


def get_persistence_config() -> PersistenceConfig:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://app:app@localhost:5432/belgian_companies",
    )
    return PersistenceConfig(database_url=url)
