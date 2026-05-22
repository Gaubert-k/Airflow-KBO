"""
DAG MS-10 — scrape par site (KBO d'abord, puis 3 sites en parallèle).

Flux : prepare → scrape_kbo → moniteur | statutes | bnb → finalize.

Conf ``enterprise_numbers`` : liste BCE (dashboard) ; sinon ``limit`` sur la file.
"""

from __future__ import annotations

import os
from datetime import datetime

from airflow.sdk.exceptions import AirflowSkipException
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param

DEFAULT_ARGS = {
    "owner": "platform",
    "depends_on_past": False,
    "retries": 0,
}

KBO_TASK_ID = "scrape_kbo"
SECONDARY_SCRAPE_TASKS: tuple[tuple[str, str], ...] = (
    ("scrape_moniteur", "moniteur"),
    ("scrape_statutes", "statutes"),
    ("scrape_bnb", "bnb"),
)


def _parse_enterprise_numbers(raw: object) -> list[str] | None:
    from packages.orchestration.scrape_parallel import parse_enterprise_numbers_param

    return parse_enterprise_numbers_param(raw)


def _parse_sources(raw: object) -> list[str]:
    from packages.orchestration.scrape_parallel import parse_sources_param

    return parse_sources_param(raw)


def _parse_bool_param(raw: object, *, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _worker_id(context) -> str:
    run_id = context.get("run_id") or ""
    if hasattr(run_id, "hex"):
        run_id = str(run_id)
    return f"airflow-{run_id}"


def _prepare_claim(**context) -> dict:
    from packages.orchestration import run_scrape_prepare

    params = context.get("params") or {}
    limit = int(params.get("limit", 10))
    numbers = _parse_enterprise_numbers(params.get("enterprise_numbers"))
    os.environ["ACQUISITION_WORKER_ID"] = _worker_id(context)
    prep = run_scrape_prepare(
        limit=limit,
        enterprise_numbers=numbers,
        worker_id=os.environ["ACQUISITION_WORKER_ID"],
    )
    prep["sources"] = _parse_sources(params.get("sources"))
    return prep


def _scrape_one_source(source: str, **context) -> dict:
    from packages.orchestration import run_scrape_source_branch

    params = context.get("params") or {}
    enabled = _parse_sources(params.get("sources"))
    if source not in enabled:
        raise AirflowSkipException(
            f"Source {source!r} absente du paramètre sources={enabled}"
        )

    ti = context["ti"]
    prep = ti.xcom_pull(task_ids="prepare_claim") or {}
    numbers = list(prep.get("enterprise_numbers") or [])

    if source != "kbo" and "kbo" in enabled:
        kbo_result = ti.xcom_pull(task_ids=KBO_TASK_ID) or {}
        ok_numbers = set(kbo_result.get("kbo_ok_numbers") or [])
        numbers = [n for n in numbers if n in ok_numbers]
        if not numbers:
            raise AirflowSkipException(
                "Aucun BCE avec KBO réussi dans ce run — branches secondaires ignorées"
            )

    wire_bridge = bool(params.get("wire_bridge", True))
    run_id = context.get("run_id") or ""
    if hasattr(run_id, "hex"):
        run_id = str(run_id)
    os.environ["ACQUISITION_WORKER_ID"] = f"airflow-{run_id}-{source}"
    from packages.orchestration.scrape_parallel import parse_parallel_requests_per_site

    parallel = parse_parallel_requests_per_site(
        params.get("parallel_requests_per_site"),
    )
    kbo_use_tor = _parse_bool_param(params.get("kbo_use_tor"), default=True)
    kbo_direct_first = _parse_bool_param(params.get("kbo_direct_first"), default=True)
    tor_loop = _parse_bool_param(params.get("tor_loop"), default=False)

    return run_scrape_source_branch(
        source,
        numbers,
        wire_bridge=wire_bridge,
        parallel_requests_per_site=parallel,
        kbo_use_tor=kbo_use_tor if source == "kbo" else None,
        tor_loop=tor_loop if source == "kbo" else None,
        kbo_direct_first=kbo_direct_first if source == "kbo" else None,
    )


def _finalize_scrape(**context) -> dict:
    from packages.orchestration import run_scrape_finalize

    ti = context["ti"]
    prep = ti.xcom_pull(task_ids="prepare_claim") or {}
    numbers = list(prep.get("enterprise_numbers") or [])
    params = context.get("params") or {}
    sources = _parse_sources(params.get("sources"))
    os.environ["ACQUISITION_WORKER_ID"] = _worker_id(context)
    return run_scrape_finalize(
        numbers,
        worker_id=os.environ["ACQUISITION_WORKER_ID"],
        sources=sources,
    )


def _failure_callback(ctx):
    from packages.orchestration.callbacks import ms10_on_failure_callback

    ms10_on_failure_callback(ctx)


with DAG(
    dag_id="02_scrape_by_source",
    default_args=DEFAULT_ARGS,
    description="MS-10 — KBO (Tor) puis moniteur / statuts / BNB sur BCE KBO OK",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-10", "scrape", "phase-b", "parallel", "tor"],
    params={
        "limit": Param(
            10,
            type="integer",
            minimum=1,
            description="Max entreprises si enterprise_numbers vide",
        ),
        "enterprise_numbers": Param(
            None,
            type=["null", "string"],
            description="N° BCE CSV ou JSON (ex. 0123456789,0987654321)",
        ),
        "sources": Param(
            "kbo,moniteur,statutes,bnb",
            type="string",
            description="Sources CSV (kbo, moniteur, statutes, bnb)",
        ),
        "wire_bridge": Param(True, type="boolean"),
        "parallel_requests_per_site": Param(
            1,
            type="integer",
            minimum=1,
            maximum=32,
            description="Requêtes HTTP simultanées par site (ex. 5 = 5 BCE en parallèle vers KBO)",
        ),
        "kbo_use_tor": Param(
            True,
            type="boolean",
            description="KBO via passes Tor (direct → tor1 → tor2 → tor3)",
        ),
        "kbo_direct_first": Param(
            True,
            type="boolean",
            description="Première passe KBO en IP directe avant Tor",
        ),
        "tor_loop": Param(
            False,
            type="boolean",
            description="Recommencer le cycle Tor (min. 10 min entre chaque cycle complet)",
        ),
    },
) as dag:
    prepare = PythonOperator(
        task_id="prepare_claim",
        python_callable=_prepare_claim,
        pool="scrape_pool",
    )
    scrape_kbo = PythonOperator(
        task_id=KBO_TASK_ID,
        python_callable=_scrape_one_source,
        op_kwargs={"source": "kbo"},
        pool="scrape_parallel_pool",
        pool_slots=1,
        retries=1,
        on_failure_callback=_failure_callback,
    )
    secondary_branches = []
    for task_id, source in SECONDARY_SCRAPE_TASKS:
        op = PythonOperator(
            task_id=task_id,
            python_callable=_scrape_one_source,
            op_kwargs={"source": source},
            pool="scrape_parallel_pool",
            pool_slots=1,
            retries=1,
            on_failure_callback=_failure_callback,
        )
        secondary_branches.append(op)
    finalize = PythonOperator(
        task_id="finalize_scrape",
        python_callable=_finalize_scrape,
        pool="scrape_pool",
        trigger_rule="all_done",
    )

    prepare >> scrape_kbo >> secondary_branches >> finalize
