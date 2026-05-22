"""Client API Airflow v2 — déclenchement DAG depuis le dashboard."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

_TOKEN: str | None = None

DAG_CATALOG: list[dict[str, Any]] = [
    {
        "dag_id": "02_scrape_by_source",
        "label": "Scrape par site (parallèle)",
        "description": "prepare → KBO (Tor) → moniteur/statuts/BNB (BCE KBO OK) → finalize.",
        "default_conf": {
            "limit": 25,
            "wire_bridge": True,
            "sources": "kbo,moniteur,statutes,bnb",
            "parallel_requests_per_site": 1,
            "kbo_use_tor": True,
            "kbo_direct_first": True,
            "tor_loop": False,
        },
        "conf_fields": [
            {"name": "limit", "type": "integer", "min": 1, "max": 500},
            {"name": "parallel_requests_per_site", "type": "integer", "min": 1, "max": 32},
            {"name": "sources", "type": "string"},
            {"name": "wire_bridge", "type": "boolean"},
            {"name": "kbo_use_tor", "type": "boolean"},
            {"name": "kbo_direct_first", "type": "boolean"},
            {"name": "tor_loop", "type": "boolean"},
        ],
        "accepts_enterprise_selection": True,
    },
    {
        "dag_id": "04_extract_batch",
        "label": "Extraction / registre",
        "description": "QUEUED_PARSE → snapshots structurés",
        "default_conf": {"limit": 25},
        "conf_fields": [{"name": "limit", "type": "integer", "min": 1, "max": 500}],
    },
    {
        "dag_id": "08_full_pipeline",
        "label": "Pipeline scrape + extract",
        "description": "Lot vertical (scrape puis extract)",
        "default_conf": {
            "limit": 10,
            "wire_bridge": True,
            "sources": "kbo,moniteur,statutes,bnb",
            "parallel_requests_per_site": 1,
            "kbo_use_tor": True,
            "kbo_direct_first": True,
            "tor_loop": False,
        },
        "conf_fields": [
            {"name": "limit", "type": "integer", "min": 1, "max": 100},
            {"name": "parallel_requests_per_site", "type": "integer", "min": 1, "max": 32},
            {"name": "sources", "type": "string"},
            {"name": "wire_bridge", "type": "boolean"},
            {"name": "kbo_use_tor", "type": "boolean"},
            {"name": "kbo_direct_first", "type": "boolean"},
            {"name": "tor_loop", "type": "boolean"},
        ],
    },
    {
        "dag_id": "07_analytics_refresh",
        "label": "Rafraîchir analytics",
        "description": "Tables analytics_* pour le dashboard",
        "default_conf": {},
        "conf_fields": [],
    },
    {
        "dag_id": "05_discovery_fanout",
        "label": "Découvertes",
        "description": "Scan snapshots → nouvelles entreprises",
        "default_conf": {"limit": 50, "hours": 48},
        "conf_fields": [
            {"name": "limit", "type": "integer", "min": 1, "max": 500},
            {"name": "hours", "type": "integer", "min": 1, "max": 720},
        ],
    },
    {
        "dag_id": "06_lifecycle_refresh",
        "label": "Cycle de vie",
        "description": "Rescrape si > 14 jours",
        "default_conf": {"limit": 50},
        "conf_fields": [{"name": "limit", "type": "integer", "min": 1, "max": 500}],
    },
]


class AirflowApiError(Exception):
    """Erreur appel API Airflow."""


def _api_base() -> str:
    return os.environ.get("AIRFLOW_API_URL", "http://airflow-apiserver:8080").rstrip("/")


def _get_token() -> str:
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    user = os.environ.get("AIRFLOW_API_USER", "airflow")
    password = os.environ.get("AIRFLOW_API_PASSWORD", "airflow")
    payload = json.dumps({"username": user, "password": password}).encode()
    req = urllib.request.Request(
        f"{_api_base()}/auth/token",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        msg = f"Auth Airflow échouée ({exc.code}): {detail}"
        raise AirflowApiError(msg) from exc
    token = body.get("access_token") or body.get("accessToken")
    if not token:
        raise AirflowApiError(f"Pas de token dans la réponse: {body}")
    _TOKEN = token
    return _TOKEN


def _request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    url = f"{_api_base()}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:800]
        raise AirflowApiError(f"{method} {path} → {exc.code}: {detail}") from exc


def list_triggerable_dags() -> list[dict[str, Any]]:
    return list(DAG_CATALOG)


def _ui_base() -> str:
    return os.environ.get("AIRFLOW_UI_URL", "http://localhost:8080").rstrip("/")


def dag_run_ui_url(dag_id: str, dag_run_id: str) -> str:
    """Lien deep vers un run dans l'UI Airflow 3."""
    rid = urllib.parse.quote(dag_run_id, safe="")
    return f"{_ui_base()}/dags/{dag_id}/runs/{rid}"


def list_recent_dag_runs(*, limit_per_dag: int = 5) -> list[dict[str, Any]]:
    """Derniers runs des DAGs du catalogue (pour affichage dashboard)."""
    rows: list[dict[str, Any]] = []
    for dag in DAG_CATALOG:
        dag_id = dag["dag_id"]
        try:
            data = _request(
                "GET",
                f"/api/v2/dags/{dag_id}/dagRuns?limit={limit_per_dag}"
                "&order_by=-start_date",
                timeout=15.0,
            )
        except AirflowApiError:
            continue
        for run in data.get("dag_runs") or []:
            run_id = run.get("dag_run_id") or run.get("run_id") or ""
            rows.append(
                {
                    "dag_id": dag_id,
                    "dag_run_id": run_id,
                    "state": run.get("state"),
                    "start_date": run.get("start_date"),
                    "end_date": run.get("end_date"),
                    "conf": run.get("conf") or {},
                    "run_url": dag_run_ui_url(dag_id, run_id) if run_id else None,
                }
            )
    rows.sort(key=lambda r: r.get("start_date") or "", reverse=True)
    return rows[:40]


def trigger_dag(dag_id: str, conf: dict[str, Any] | None = None) -> dict[str, Any]:
    """Déclenche un DAG run manuel."""
    known = {d["dag_id"] for d in DAG_CATALOG}
    if dag_id not in known:
        msg = f"DAG non autorisé depuis le dashboard: {dag_id}"
        raise AirflowApiError(msg)
    now = datetime.now(UTC).isoformat()
    payload: dict[str, Any] = {
        "conf": conf or {},
        "logical_date": now,
    }
    result = _request("POST", f"/api/v2/dags/{dag_id}/dagRuns", body=payload)
    run_id = result.get("dag_run_id") or result.get("run_id") or ""
    return {
        "dag_id": dag_id,
        "dag_run_id": run_id,
        "state": result.get("state"),
        "conf": conf or {},
        "airflow_ui_url": _ui_base(),
        "run_url": dag_run_ui_url(dag_id, run_id) if run_id else None,
    }
