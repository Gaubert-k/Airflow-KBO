"""Politique de fraîcheur MS-07."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LifecycleConfig:
    max_age_days: int = 14


def get_lifecycle_config() -> LifecycleConfig:
    return LifecycleConfig(max_age_days=int(os.environ.get("LIFECYCLE_MAX_AGE_DAYS", "14")))
