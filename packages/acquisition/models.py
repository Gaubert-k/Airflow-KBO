"""Modèles MS-02 — jobs, résultats, décisions de validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ValidationAction(StrEnum):
    STORE = "STORE"
    DROP = "DROP"
    RETRY = "RETRY"


@dataclass(frozen=True)
class FetchJob:
    url: str
    source: str
    doc_type: str
    enterprise_number: str


@dataclass
class FetchResult:
    body: bytes | None
    http_status: int | None
    headers: dict[str, str] = field(default_factory=dict)
    timing_ms: float = 0.0
    proxy_or_ip: str = "direct"
    attempt_count: int = 1
    url: str = ""
    final_url: str = ""
    error: str | None = None


@dataclass(frozen=True)
class ValidationDecision:
    action: ValidationAction
    reason_code: str
    detail: str | None = None


# Codes stables (FREEZE)
REASON_HTTP_2XX = "HTTP_2XX"
REASON_HTTP_4XX = "HTTP_4XX"
REASON_HTTP_5XX = "HTTP_5XX"
REASON_HTTP_OTHER = "HTTP_OTHER"
REASON_EMPTY_BODY = "EMPTY_BODY"
REASON_HTML_ERROR_MARKER = "HTML_ERROR_MARKER"
REASON_CAPTCHA_SUSPECT = "CAPTCHA_SUSPECT"


class CaptchaBlockedError(RuntimeError):
    """Site bloqué (captcha) — la task Airflow doit échouer immédiatement."""
REASON_PROXY_TUNNEL_FAILED = "PROXY_TUNNEL_FAILED"
REASON_FETCH_ERROR = "FETCH_ERROR"
REASON_CONTENT_TYPE_MISMATCH = "CONTENT_TYPE_MISMATCH"
REASON_HTTP_404 = "HTTP_404"
