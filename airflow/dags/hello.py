"""
DAG de validation MS-00 — preuve qu'Airflow parse et exécute.

Bonnes pratiques :
- Imports Airflow uniquement au niveau module (légers).
- Logique métier / imports lourds : dans le corps des callables de task.
"""

from __future__ import annotations

from datetime import datetime

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

DEFAULT_ARGS = {
    "owner": "platform",
    "depends_on_past": False,
    "retries": 0,
}


def _say_hello() -> str:
    """Task callable : imports métier autorisés ici, pas en tête de DAG."""
    # Exemple d'import différé (léger pour MS-00) :
    from packages.platform.logging import configure_structured_logging

    configure_structured_logging()
    import logging

    logging.getLogger(__name__).info("Hello from MS-00 foundation DAG")
    return "hello-ok"


with DAG(
    dag_id="00_hello",
    default_args=DEFAULT_ARGS,
    description="DAG fondation MS-00 — smoke test Airflow",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-00", "foundation"],
) as dag:
    PythonOperator(
        task_id="say_hello",
        python_callable=_say_hello,
    )
