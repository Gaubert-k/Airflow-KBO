"""Sérialisation des rapports MS-01 / MS-02 pour XCom Airflow."""

from __future__ import annotations

from typing import Any

from packages.ingestion.report import IngestReport


def ingest_report_to_dict(report: IngestReport) -> dict[str, Any]:
    return {
        "rows_read": report.rows_read,
        "created": report.created,
        "already_existed": report.already_existed,
        "rejected": report.rejected,
        "quarantine_path": str(report.quarantine_path) if report.quarantine_path else None,
        "source_file": str(report.source_file),
        "duration_seconds": report.duration_seconds,
    }


def scrape_report_to_dict(report: object) -> dict[str, Any]:
    return {
        "claimed": report.claimed,
        "succeeded": report.succeeded,
        "failed": report.failed,
        "enterprises": list(report.enterprises),
    }


def parse_report_to_dict(report: object) -> dict[str, Any]:
    return {
        "claimed": report.claimed,
        "succeeded": report.succeeded,
        "failed": report.failed,
        "enterprises": list(report.enterprises),
    }


def lifecycle_report_to_dict(report: object) -> dict[str, Any]:
    return {
        "due_selected": report.due_selected,
        "queued": report.queued,
        "statuses_updated": report.statuses_updated,
    }


def analytics_report_to_dict(report: object) -> dict[str, Any]:
    return {
        "run_id": report.run_id,
        "postal_rows": report.postal_rows,
        "state_rows": report.state_rows,
        "activity_rows": report.activity_rows,
        "stale_flag": report.stale_flag,
    }
