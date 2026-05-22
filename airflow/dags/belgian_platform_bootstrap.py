"""
DAG bootstrap — première ouverture du volume ``data/`` uniquement.

Ingest tous les CSV → scrape massif (lots) → extract → analytics → marqueur
``data/.platform_initialized``.

Déclenché automatiquement par ``scripts/bootstrap-if-empty.sh`` au ``docker compose up``
si le volume est vierge. Ne pas relancer manuellement sauf reset complet des données.
"""

from __future__ import annotations

import os
from datetime import datetime

from airflow.sdk.exceptions import AirflowSkipException
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param

DEFAULT_ARGS = {"owner": "platform", "depends_on_past": False, "retries": 0}


def _gate_fresh_volume(**context) -> dict:
    from packages.platform.volume_bootstrap import is_data_volume_uninitialized

    params = context.get("params") or {}
    if bool(params.get("force", False)):
        return {"fresh": True, "forced": True}
    if not is_data_volume_uninitialized():
        raise AirflowSkipException(
            "Volume data déjà initialisé (.platform_initialized ou données présentes) — "
            "bootstrap ignoré"
        )
    return {"fresh": True}


def _run_full_bootstrap(**context) -> dict:
    from packages.orchestration.bootstrap_workflow import run_platform_bootstrap

    params = context.get("params") or {}
    run_id = str(context.get("run_id", ""))
    if hasattr(run_id, "hex"):
        run_id = str(run_id)
    os.environ["ACQUISITION_WORKER_ID"] = f"airflow-bootstrap-{run_id}"
    raw_dirs = str(params.get("csv_dirs", "")).strip()
    csv_dirs = [d.strip() for d in raw_dirs.split(",") if d.strip()] or None

    return run_platform_bootstrap(
        worker_id=os.environ["ACQUISITION_WORKER_ID"],
        csv_dirs=csv_dirs,
        ingest_batch_size=int(params.get("ingest_batch_size", 50_000)),
        scrape_batch_limit=int(params.get("scrape_batch_limit", 0)) or None,
        scrape_max_batches=int(params.get("scrape_max_batches", 0)),
        extract_batch_limit=int(params.get("extract_batch_limit", 0)) or None,
        extract_max_batches=int(params.get("extract_max_batches", 0)),
        parallel_requests_per_site=int(params.get("parallel_requests_per_site", 5)),
        wire_bridge=bool(params.get("wire_bridge", True)),
        force=bool(params.get("force", False)),
    )


with DAG(
    dag_id="09_platform_bootstrap",
    default_args=DEFAULT_ARGS,
    description="Init unique — ingest + scrape massif + extract (volume data vide)",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-10", "bootstrap", "phase-b"],
    params={
        "force": Param(
            False,
            type="boolean",
            description="Forcer même si marqueur présent (danger)",
        ),
        "csv_dirs": Param(
            "/opt/airflow/data/seed/csv,/opt/airflow/data/input/csv",
            type="string",
        ),
        "ingest_batch_size": Param(50_000, type="integer", minimum=1000),
        "scrape_batch_limit": Param(
            0,
            type="integer",
            minimum=0,
            description="BCE par lot scrape (0 = env PLATFORM_BOOTSTRAP_SCRAPE_BATCH, défaut 2000)",
        ),
        "scrape_max_batches": Param(
            0,
            type="integer",
            minimum=0,
            description="0 = jusqu'à file QUEUED_SCRAPE vide (plafond sécurité 10000)",
        ),
        "extract_batch_limit": Param(0, type="integer", minimum=0),
        "extract_max_batches": Param(0, type="integer", minimum=0),
        "parallel_requests_per_site": Param(5, type="integer", minimum=1, maximum=32),
        "wire_bridge": Param(True, type="boolean"),
    },
) as dag:
    gate = PythonOperator(
        task_id="gate_fresh_volume",
        python_callable=_gate_fresh_volume,
        pool="ingest_pool",
    )
    bootstrap = PythonOperator(
        task_id="run_full_bootstrap",
        python_callable=_run_full_bootstrap,
        pool="ingest_pool",
    )
    gate >> bootstrap
