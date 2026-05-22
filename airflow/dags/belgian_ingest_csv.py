"""
DAG MS-10 — ingestion unique : tous les CSV entreprise → base PostgreSQL.

Parcourt ``data/seed/csv`` + ``data/input/csv`` (fichiers avec colonne
EnterpriseNumber / EntityNumber / enterprise_number). Ignore meta.csv, code.csv, etc.

À lancer **une fois** ; ensuite uniquement les DAGs scrape (02, 02b, 03).
"""

from __future__ import annotations

from datetime import datetime

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param

DEFAULT_ARGS = {
    "owner": "platform",
    "depends_on_past": False,
    "retries": 0,
}

DEFAULT_DIRS_CSV = (
    "/opt/airflow/data/seed/csv,/opt/airflow/data/input/csv"
)


def _ingest_all_from_params(**context) -> dict:
    from packages.orchestration import run_ingest_all_csv

    params = context.get("params") or {}
    raw_dirs = str(params.get("csv_dirs", DEFAULT_DIRS_CSV)).strip()
    csv_dirs = [d.strip() for d in raw_dirs.split(",") if d.strip()]
    column = params.get("column")
    column_str = str(column).strip() if column not in (None, "") else None
    batch_size = int(params.get("batch_size", 50000))

    return run_ingest_all_csv(csv_dirs, column=column_str, batch_size=batch_size)


with DAG(
    dag_id="01_ingest_csv",
    default_args=DEFAULT_ARGS,
    description="MS-10 — tous les CSV entreprise → DB (une passe, idempotent)",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-10", "ingest", "phase-b", "bootstrap"],
    params={
        "csv_dirs": Param(
            DEFAULT_DIRS_CSV,
            type="string",
            description="Répertoires CSV séparés par des virgules (seed + input)",
        ),
        "column": Param(
            None,
            type=["null", "string"],
            description="Forcer le nom de colonne pour tous les fichiers (optionnel)",
        ),
        "batch_size": Param(50000, type="integer", minimum=1),
    },
) as dag:
    PythonOperator(
        task_id="ingest_all",
        python_callable=_ingest_all_from_params,
        pool="ingest_pool",
        retries=1,
        on_failure_callback=lambda ctx: __import__(
            "packages.orchestration.callbacks",
            fromlist=["ms10_on_failure_callback"],
        ).ms10_on_failure_callback(ctx),
    )
