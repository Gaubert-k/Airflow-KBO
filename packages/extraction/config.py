"""Configuration MS-04."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractionConfig:
    extractor_version: str = "1.0.0"
    schema_version: int = 1
    worker_id: str = "extraction-worker-1"


def get_extraction_config() -> ExtractionConfig:
    return ExtractionConfig(
        extractor_version=os.environ.get("EXTRACTION_VERSION", "1.0.0"),
        schema_version=int(os.environ.get("EXTRACTION_SCHEMA_VERSION", "1")),
        worker_id=os.environ.get("EXTRACTION_WORKER_ID", "extraction-worker-1"),
    )
