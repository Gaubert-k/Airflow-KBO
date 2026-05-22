"""Hooks d'observabilité MS-10 (T10.4)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def ms10_on_failure_callback(context: dict[str, Any]) -> None:
    """Log structuré en cas d'échec de tâche ingest/scrape."""
    ti = context.get("task_instance")
    dag_id = getattr(ti, "dag_id", None) or context.get("dag", {}).get("dag_id")
    task_id = getattr(ti, "task_id", None) or context.get("task", {}).get("task_id")
    run_id = context.get("run_id") or getattr(context.get("dag_run"), "run_id", None)

    logger.error(
        "MS-10 task failed",
        extra={
            "dag_id": dag_id,
            "task_id": task_id,
            "run_id": run_id,
            "ms": "MS-10",
        },
    )

    try:
        from packages.acquisition.metrics import snapshot

        metrics = snapshot()
        if any(metrics.values()):
            logger.info(
                "acquisition metrics snapshot (read-only)",
                extra={"dag_id": dag_id, "task_id": task_id, "metrics": metrics},
            )
    except Exception:
        logger.debug("metrics snapshot unavailable", exc_info=True)
