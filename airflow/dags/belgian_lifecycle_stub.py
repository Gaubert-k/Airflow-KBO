"""DAG MS-10 phase C — fraîcheur / rescrape (MS-07)."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param

DEFAULT_ARGS = {"owner": "platform", "depends_on_past": False, "retries": 0}


def _lifecycle_from_params(**context) -> dict:
    from packages.orchestration import run_lifecycle_tick

    params = context.get("params") or {}
    return run_lifecycle_tick(limit=int(params.get("limit", 50)))


with DAG(
    dag_id="06_lifecycle_refresh",
    default_args=DEFAULT_ARGS,
    description="MS-07/10 — entreprises dues (>14j) → QUEUED_SCRAPE",
    schedule=timedelta(days=1),
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-10", "lifecycle", "phase-c"],
    params={"limit": Param(50, type="integer", minimum=1)},
) as dag:
    PythonOperator(task_id="lifecycle_tick", python_callable=_lifecycle_from_params)
