"""T02.3 — validate_fetch(result) -> ValidationDecision."""

from __future__ import annotations

import re

from packages.acquisition.models import (
    REASON_CAPTCHA_SUSPECT,
    REASON_CONTENT_TYPE_MISMATCH,
    REASON_EMPTY_BODY,
    REASON_FETCH_ERROR,
    REASON_HTML_ERROR_MARKER,
    REASON_HTTP_2XX,
    REASON_HTTP_4XX,
    REASON_HTTP_5XX,
    REASON_HTTP_404,
    REASON_HTTP_OTHER,
    REASON_PROXY_TUNNEL_FAILED,
    FetchResult,
    ValidationAction,
    ValidationDecision,
)

_CAPTCHA_MARKERS = (
    re.compile(r"captcha", re.I),
    re.compile(r"recaptcha", re.I),
    re.compile(r"are you a robot", re.I),
)

_CAPTCHA_URL_FRAGMENTS = (
    "captchaform.html",
    "captchaform",
    "/captcha",
)

# Page-level errors only — not field placeholders (e.g. KBO « Geen gegevens opgenomen in KBO »).
_ERROR_MARKERS = (
    re.compile(r"<title[^>]*>\s*404", re.I),
    re.compile(r"page\s+not\s+found", re.I),
    re.compile(r"aucune\s+donnée", re.I),
    re.compile(r"geen\s+onderneming", re.I),
    re.compile(r"onderneming\s+niet\s+gevonden", re.I),
    re.compile(r"numéro\s+d'entreprise.*introuvable", re.I),
)

_MIN_HTML_BYTES = 64


def validate_fetch(result: FetchResult) -> ValidationDecision:
    if result.error:
        if result.proxy_or_ip not in ("direct", "none") and (
            "proxy" in result.error.lower()
            or "tunnel" in result.error.lower()
            or "connection refused" in result.error.lower()
            or "timed out" in result.error.lower()
        ):
            return ValidationDecision(
                ValidationAction.RETRY,
                REASON_PROXY_TUNNEL_FAILED,
                result.error,
            )
        return ValidationDecision(ValidationAction.RETRY, REASON_FETCH_ERROR, result.error)

    status = result.http_status
    if status is None:
        return ValidationDecision(ValidationAction.RETRY, REASON_FETCH_ERROR, "missing http_status")

    if status == 404:
        return ValidationDecision(ValidationAction.DROP, REASON_HTTP_404, f"status={status}")

    if 400 <= status < 500:
        if status in (403, 429):
            reason = REASON_CAPTCHA_SUSPECT if status == 403 else REASON_HTTP_4XX
            return ValidationDecision(ValidationAction.RETRY, reason, f"status={status}")
        return ValidationDecision(ValidationAction.DROP, REASON_HTTP_4XX, f"status={status}")

    if status >= 500:
        return ValidationDecision(ValidationAction.RETRY, REASON_HTTP_5XX, f"status={status}")

    if status < 200 or status >= 300:
        return ValidationDecision(ValidationAction.DROP, REASON_HTTP_OTHER, f"status={status}")

    body = result.body
    if not body:
        return ValidationDecision(ValidationAction.RETRY, REASON_EMPTY_BODY, "empty body")

    content_type = (result.headers.get("content-type") or "").lower()
    is_html = (
        "html" in content_type
        or body.lstrip()[:15].lower().startswith(b"<!doctype html")
        or body.lstrip()[:6].lower().startswith(b"<html")
    )

    if not is_html and content_type and "text" not in content_type:
        return ValidationDecision(
            ValidationAction.DROP,
            REASON_CONTENT_TYPE_MISMATCH,
            content_type,
        )

    resolved = (result.final_url or result.url or "").lower()
    for frag in _CAPTCHA_URL_FRAGMENTS:
        if frag in resolved:
            return ValidationDecision(
                ValidationAction.RETRY,
                REASON_CAPTCHA_SUSPECT,
                f"url:{frag}",
            )

    if is_html:
        if len(body) < _MIN_HTML_BYTES:
            return ValidationDecision(ValidationAction.RETRY, REASON_EMPTY_BODY, "html too small")

        text = body.decode("utf-8", errors="replace")
        for pattern in _CAPTCHA_MARKERS:
            if pattern.search(text):
                return ValidationDecision(
                    ValidationAction.RETRY,
                    REASON_CAPTCHA_SUSPECT,
                    pattern.pattern,
                )
        for pattern in _ERROR_MARKERS:
            if pattern.search(text):
                return ValidationDecision(
                    ValidationAction.DROP,
                    REASON_HTML_ERROR_MARKER,
                    pattern.pattern,
                )

    return ValidationDecision(ValidationAction.STORE, REASON_HTTP_2XX)
