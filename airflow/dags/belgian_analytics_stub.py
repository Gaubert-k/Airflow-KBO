"""DAG MS-10 phase C — analytics périodiques (MS-08)."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

DEFAULT_ARGS = {"owner": "platform", "depends_on_past": False, "retries": 0}


def _analytics_refresh(**_context) -> dict:
    from packages.orchestration import run_analytics_refresh

    return run_analytics_refresh()


with DAG(
    dag_id="07_analytics_refresh",
    default_args=DEFAULT_ARGS,
    description="MS-08/10 — rafraîchit tables analytics_postal/state/activity",
    schedule=timedelta(days=1),
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-10", "analytics", "phase-c"],
) as dag:
    PythonOperator(task_id="analytics_refresh", python_callable=_analytics_refresh)
