"""DAG MS-10 phase C — extraction HTML → structuré (MS-04)."""

from __future__ import annotations

import os
from datetime import datetime

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param

DEFAULT_ARGS = {"owner": "platform", "depends_on_past": False, "retries": 0}


def _extract_from_params(**context) -> dict:
    from packages.orchestration import run_parse_batch

    params = context.get("params") or {}
    limit = int(params.get("limit", 10))
    run_id = context.get("run_id") or ""
    if hasattr(run_id, "hex"):
        run_id = str(run_id)
    os.environ["EXTRACTION_WORKER_ID"] = f"airflow-extract-{run_id}"
    return run_parse_batch(limit=limit)


with DAG(
    dag_id="04_extract_batch",
    default_args=DEFAULT_ARGS,
    description="MS-04/10 — parse QUEUED_PARSE → snapshots + discovery",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-10", "extract", "phase-c"],
    params={"limit": Param(10, type="integer", minimum=1)},
) as dag:
    PythonOperator(
        task_id="extract",
        python_callable=_extract_from_params,
        pool="scrape_pool",
        on_failure_callback=lambda ctx: __import__(
            "packages.orchestration.callbacks",
            fromlist=["ms10_on_failure_callback"],
        ).ms10_on_failure_callback(ctx),
    )
