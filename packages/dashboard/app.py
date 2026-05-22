"""Application FastAPI — supervision temps quasi réel (MS-09)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from packages.dashboard.airflow_client import (
    AirflowApiError,
    list_recent_dag_runs,
    list_triggerable_dags,
    trigger_dag,
)
from packages.dashboard.enterprises import (
    EnterpriseActionError,
    force_parse_enterprise,
    get_enterprise_detail,
    list_enterprises,
)
from packages.persistence.exceptions import EnterpriseNotFoundError
from packages.monitoring.events import (
    get_analytics_snapshot,
    get_recent_pipeline_events,
    get_supervision_snapshot,
)

_STATIC = Path(__file__).resolve().parent / "static"
_DASHBOARD_TOKEN = os.environ.get("DASHBOARD_TOKEN", "")
_AIRFLOW_UI_URL = os.environ.get("AIRFLOW_UI_URL", "http://localhost:8080")

app = FastAPI(title="Belgian Companies — Supervision", version="0.3.0")
app.mount(
    "/static",
    StaticFiles(directory=_STATIC, html=False),
    name="static",
)


def _check_auth(authorization: str | None) -> None:
    if not _DASHBOARD_TOKEN:
        return
    if authorization != f"Bearer {_DASHBOARD_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config(authorization: str | None = Header(default=None)) -> dict[str, str]:
    _check_auth(authorization)
    return {
        "airflow_ui_url": _AIRFLOW_UI_URL,
        "refresh_hint_seconds": "15",
    }


@app.get("/api/supervision")
def supervision(authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)
    return get_supervision_snapshot()


@app.get("/api/analytics")
def analytics(authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)
    return get_analytics_snapshot()


@app.get("/api/events")
def events(
    authorization: str | None = Header(default=None),
    limit: int = 30,
) -> list[dict]:
    _check_auth(authorization)
    return get_recent_pipeline_events(limit=min(limit, 100))


@app.get("/api/enterprises")
def enterprises_list(
    authorization: str | None = Header(default=None),
    page: int = 1,
    page_size: int = 50,
    state: str | None = None,
    q: str | None = None,
    sort: str = "recent_scrape",
    light: bool = False,
) -> dict:
    _check_auth(authorization)
    return list_enterprises(
        page=page,
        page_size=page_size,
        state=state,
        q=q,
        sort=sort,
        light=light,
    )


@app.get("/api/enterprises/{enterprise_number}")
def enterprise_detail(
    enterprise_number: str,
    authorization: str | None = Header(default=None),
) -> dict:
    _check_auth(authorization)
    try:
        return get_enterprise_detail(enterprise_number)
    except EnterpriseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/dags")
def dags_catalog(authorization: str | None = Header(default=None)) -> list[dict]:
    _check_auth(authorization)
    return list_triggerable_dags()


class DagTriggerBody(BaseModel):
    conf: dict | None = None


def _normalize_dag_conf(conf: dict) -> dict:
    """Airflow Param ``enterprise_numbers`` : string CSV, pas liste JSON."""
    out = dict(conf)
    raw = out.get("enterprise_numbers")
    if isinstance(raw, list):
        out["enterprise_numbers"] = ",".join(
            str(n).strip() for n in raw if str(n).strip()
        )
    return out


@app.get("/api/dags/runs/recent")
def dags_recent_runs(authorization: str | None = Header(default=None)) -> list[dict]:
    _check_auth(authorization)
    try:
        return list_recent_dag_runs()
    except AirflowApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/dags/{dag_id}/trigger")
def dag_trigger(
    dag_id: str,
    body: DagTriggerBody | None = None,
    authorization: str | None = Header(default=None),
) -> dict:
    _check_auth(authorization)
    try:
        raw_conf = (body.conf if body else None) or {}
        return trigger_dag(dag_id, _normalize_dag_conf(raw_conf))
    except AirflowApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _run_background_parse(number: str) -> None:
    try:
        force_parse_enterprise(number)
    except Exception:
        pass


@app.post("/api/enterprises/{enterprise_number}/scrape")
def enterprise_force_scrape(
    enterprise_number: str,
    authorization: str | None = Header(default=None),
) -> dict:
    """Scrape direct désactivé — uniquement via DAG Airflow (02_scrape_by_source)."""
    _check_auth(authorization)
    raise HTTPException(
        status_code=403,
        detail=(
            "Le scrape direct est désactivé. "
            "Utilisez l'onglet DAGs Airflow (02_scrape_by_source ou 08_full_pipeline)."
        ),
    )


@app.post("/api/enterprises/{enterprise_number}/parse")
def enterprise_force_parse(
    enterprise_number: str,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    sync: bool = False,
) -> dict:
    _check_auth(authorization)
    if sync:
        try:
            return force_parse_enterprise(enterprise_number)
        except EnterpriseActionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(_run_background_parse, enterprise_number)
    return {
        "enterprise_number": enterprise_number,
        "queued": True,
        "message": "Parse lancé en arrière-plan",
    }


@app.get("/")
def home(authorization: str | None = Header(default=None)) -> FileResponse:
    _check_auth(authorization)
    return FileResponse(_STATIC / "index.html")
