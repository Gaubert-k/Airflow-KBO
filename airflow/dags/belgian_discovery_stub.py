"""DAG MS-10 phase C — fan-out découverte (MS-06)."""

from __future__ import annotations

from datetime import datetime

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param

DEFAULT_ARGS = {"owner": "platform", "depends_on_past": False, "retries": 0}


def _discovery_from_params(**context) -> dict:
    from packages.orchestration import run_discovery_fanout

    params = context.get("params") or {}
    return run_discovery_fanout(
        hours=int(params.get("hours", 48)),
        limit=int(params.get("limit", 50)),
    )


with DAG(
    dag_id="05_discovery_fanout",
    default_args=DEFAULT_ARGS,
    description="MS-06/10 — scan snapshots récents et enqueue découvertes",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-10", "discovery", "phase-c"],
    params={
        "hours": Param(48, type="integer", minimum=1),
        "limit": Param(50, type="integer", minimum=1),
    },
) as dag:
    PythonOperator(task_id="discovery_fanout", python_callable=_discovery_from_params)
