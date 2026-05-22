"""Tests MS-09 — dashboard FastAPI (sans PostgreSQL pour les routes légères)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from packages.dashboard.app import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_config_exposes_airflow_url() -> None:
    body = client.get("/api/config").json()
    assert "airflow_ui_url" in body
    assert body["airflow_ui_url"].startswith("http")


@patch("packages.dashboard.app.get_supervision_snapshot")
def test_supervision_route(mock_snap) -> None:
    mock_snap.return_value = {
        "generated_at": "2026-05-21T12:00:00+00:00",
        "in_flight": 1,
        "pending": 2,
        "queue_by_state": {"NEW": 2},
    }
    body = client.get("/api/supervision").json()
    assert body["in_flight"] == 1
    mock_snap.assert_called_once()


@patch("packages.dashboard.app.get_analytics_snapshot")
def test_analytics_route(mock_analytics) -> None:
    mock_analytics.return_value = {"empty": True, "postal": [], "states": [], "activities": []}
    body = client.get("/api/analytics").json()
    assert body["empty"] is True


@patch("packages.dashboard.app._check_auth")
def test_home_serves_html(_mock_auth) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Plateforme entreprises belges" in r.text
    assert "/static/app.js" in r.text
    assert "Entreprises" in r.text
    assert "tab-panel" in r.text


@patch("packages.dashboard.app.get_enterprise_detail")
def test_enterprise_detail_route(mock_detail) -> None:
    mock_detail.return_value = {
        "enterprise_number": "0203430576",
        "processing": {"state": "STRUCTURED"},
        "raw_documents": [],
        "latest_snapshot": None,
    }
    body = client.get("/api/enterprises/0203430576").json()
    assert body["enterprise_number"] == "0203430576"
    mock_detail.assert_called_once()


def test_dag_catalog_excludes_legacy_batch_scrape() -> None:
    from packages.dashboard.airflow_client import DAG_CATALOG

    ids = {d["dag_id"] for d in DAG_CATALOG}
    assert "02_scrape_by_source" in ids
    assert "02_scrape_batch" not in ids


@patch("packages.dashboard.app.trigger_dag")
def test_dag_trigger_route(mock_trigger) -> None:
    mock_trigger.return_value = {"dag_id": "02_scrape_by_source", "dag_run_id": "manual__x"}
    body = client.post(
        "/api/dags/02_scrape_by_source/trigger",
        json={"conf": {"limit": 5, "wire_bridge": True, "sources": "kbo,bnb"}},
    ).json()
    assert body["dag_run_id"] == "manual__x"
    mock_trigger.assert_called_once()


@patch("packages.dashboard.app.list_enterprises")
def test_enterprises_list_route(mock_list) -> None:
    mock_list.return_value = {
        "page": 1,
        "page_size": 50,
        "total": 1,
        "total_pages": 1,
        "items": [
            {
                "enterprise_number": "0203430576",
                "state": "STRUCTURED",
                "last_scrape_at": None,
                "raw_doc_count": 0,
                "has_registry": True,
            }
        ],
    }
    body = client.get("/api/enterprises?q=0203").json()
    assert body["total"] == 1
    assert body["items"][0]["enterprise_number"] == "0203430576"
    mock_list.assert_called_once()
