"""
DAG MS-10 phase B — lot de scraping (glue uniquement).

Parse-time : pas d'import packages.acquisition / packages.ingestion.
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


def _parse_sources_param(raw: object) -> list[str] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, list):
        return [str(s).strip().lower() for s in raw if str(s).strip()]
    text = str(raw).strip()
    if not text:
        return None
    return [s.strip().lower() for s in text.split(",") if s.strip()]


def _parse_enterprise_numbers(raw: object) -> list[str] | None:
    from packages.orchestration.scrape_parallel import parse_enterprise_numbers_param

    return parse_enterprise_numbers_param(raw)


def _scrape_from_params(**context) -> dict:
    from packages.orchestration import run_scrape_batch

    params = context.get("params") or {}
    limit = int(params.get("limit", 10))
    sources = _parse_sources_param(params.get("sources"))
    numbers = _parse_enterprise_numbers(params.get("enterprise_numbers"))
    wire_bridge = bool(params.get("wire_bridge", True))

    run_id = context.get("run_id") or ""
    if hasattr(run_id, "hex"):
        run_id = str(run_id)
    os.environ["ACQUISITION_WORKER_ID"] = f"airflow-{run_id}"

    return run_scrape_batch(
        limit=limit,
        enterprise_numbers=numbers,
        sources=sources,
        wire_bridge=wire_bridge,
    )


with DAG(
    dag_id="02_scrape_batch",
    default_args=DEFAULT_ARGS,
    description="MS-10 — scrape batch (QUEUED_SCRAPE → HDFS / états MS-02)",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-10", "scrape", "phase-b"],
    params={
        "limit": Param(10, type="integer", minimum=1),
        "sources": Param(
            None,
            type=["null", "string"],
            description="Sources CSV optionnel (ex. kbo,moniteur) ; vide = toutes",
        ),
        "enterprise_numbers": Param(
            None,
            type=["null", "string"],
            description="N° BCE optionnels (CSV) ; vide = file QUEUED_SCRAPE",
        ),
        "wire_bridge": Param(True, type="boolean", description="Activer wire_storage_events (MS-05)"),
    },
) as dag:
    PythonOperator(
        task_id="scrape",
        python_callable=_scrape_from_params,
        pool="scrape_pool",
        retries=1,
        on_failure_callback=lambda ctx: __import__(
            "packages.orchestration.callbacks",
            fromlist=["ms10_on_failure_callback"],
        ).ms10_on_failure_callback(ctx),
    )
