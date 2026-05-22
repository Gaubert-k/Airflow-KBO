"""
DAG MS-10 phase B — scrape par site (après ingestion unique ``01_ingest_csv``).

Ne ré-ingère pas les CSV : la base est déjà remplie. 4 tasks parallèles pour
voir quel site (kbo / moniteur / statutes / bnb) est bloqué.
"""

from __future__ import annotations

import os
from datetime import datetime

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param

DEFAULT_ARGS = {
    "owner": "platform",
    "depends_on_past": False,
    "retries": 0,
}

SCRAPE_SOURCE_TASKS: tuple[tuple[str, str], ...] = (
    ("scrape_kbo", "kbo"),
    ("scrape_moniteur", "moniteur"),
    ("scrape_statutes", "statutes"),
    ("scrape_bnb", "bnb"),
)


def _pipeline_scrape_source(source: str, **context) -> dict:
    from packages.orchestration import run_scrape_single_source

    params = context.get("params") or {}
    limit = int(params.get("limit", 10))
    wire_bridge = bool(params.get("wire_bridge", True))

    run_id = context.get("run_id") or ""
    if hasattr(run_id, "hex"):
        run_id = str(run_id)
    os.environ["ACQUISITION_WORKER_ID"] = f"airflow-{run_id}-{source}"

    return run_scrape_single_source(source, limit=limit, wire_bridge=wire_bridge)


def _failure_callback(ctx):
    from packages.orchestration.callbacks import ms10_on_failure_callback

    ms10_on_failure_callback(ctx)


with DAG(
    dag_id="03_pipeline_dev",
    default_args=DEFAULT_ARGS,
    description="MS-10 — scrape dev par site (prérequis : 01_ingest_csv déjà exécuté)",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-10", "scrape", "phase-b", "dev", "parallel"],
    params={
        "limit": Param(10, type="integer", minimum=1),
        "wire_bridge": Param(True, type="boolean"),
    },
) as dag:
    for task_id, source in SCRAPE_SOURCE_TASKS:
        PythonOperator(
            task_id=task_id,
            python_callable=_pipeline_scrape_source,
            op_kwargs={"source": source},
            pool="scrape_pool",
            retries=1,
            on_failure_callback=_failure_callback,
        )
