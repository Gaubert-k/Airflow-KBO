"""DAG MS-10 — pipeline vertical prepare → KBO Tor → autres sites → extract."""

from __future__ import annotations

import os
from datetime import datetime

from airflow.sdk.exceptions import AirflowSkipException
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param

DEFAULT_ARGS = {"owner": "platform", "depends_on_past": False, "retries": 0}

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


def _worker_id(context, *, suffix: str = "") -> str:
    run_id = str(context.get("run_id", ""))
    if hasattr(run_id, "hex"):
        run_id = str(run_id)
    base = f"airflow-full-{run_id}"
    return f"{base}-{suffix}" if suffix else base


def _prepare_claim(**context) -> dict:
    from packages.orchestration import run_scrape_prepare

    params = context.get("params") or {}
    os.environ["ACQUISITION_WORKER_ID"] = _worker_id(context)
    prep = run_scrape_prepare(
        limit=int(params.get("limit", 5)),
        enterprise_numbers=_parse_enterprise_numbers(params.get("enterprise_numbers")),
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
                "Aucun BCE avec KBO réussi — branches secondaires ignorées"
            )

    os.environ["ACQUISITION_WORKER_ID"] = _worker_id(context, suffix=source)
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
        wire_bridge=bool(params.get("wire_bridge", True)),
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
    os.environ["ACQUISITION_WORKER_ID"] = _worker_id(context)
    return run_scrape_finalize(
        numbers,
        worker_id=os.environ["ACQUISITION_WORKER_ID"],
        sources=_parse_sources(params.get("sources")),
    )


def _extract(**context) -> dict:
    from packages.orchestration import run_parse_batch

    params = context.get("params") or {}
    run_id = str(context.get("run_id", ""))
    os.environ["EXTRACTION_WORKER_ID"] = f"airflow-full-{run_id}"
    return run_parse_batch(limit=int(params.get("limit", 5)))


with DAG(
    dag_id="08_full_pipeline",
    default_args=DEFAULT_ARGS,
    description="MS-10 — KBO Tor puis autres sites (BCE KBO OK) puis extract",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ms-10", "pipeline", "phase-c", "tor"],
    params={
        "limit": Param(5, type="integer", minimum=1),
        "sources": Param(
            "kbo,moniteur,statutes,bnb",
            type="string",
            description="Sources CSV pour le scrape",
        ),
        "wire_bridge": Param(True, type="boolean"),
        "parallel_requests_per_site": Param(
            1,
            type="integer",
            minimum=1,
            maximum=32,
            description="Requêtes HTTP simultanées par site",
        ),
        "kbo_use_tor": Param(True, type="boolean"),
        "kbo_direct_first": Param(True, type="boolean"),
        "tor_loop": Param(False, type="boolean"),
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
    )
    secondary_branches = []
    for task_id, source in SECONDARY_SCRAPE_TASKS:
        op = PythonOperator(
            task_id=task_id,
            python_callable=_scrape_one_source,
            op_kwargs={"source": source},
            pool="scrape_parallel_pool",
            pool_slots=1,
        )
        secondary_branches.append(op)
    finalize = PythonOperator(
        task_id="finalize_scrape",
        python_callable=_finalize_scrape,
        pool="scrape_pool",
        trigger_rule="all_done",
    )
    extract = PythonOperator(
        task_id="extract",
        python_callable=_extract,
        pool="scrape_pool",
    )

    prepare >> scrape_kbo >> secondary_branches >> finalize >> extract
