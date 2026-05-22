"""Métriques MS-02 (stub MS-09) — compteurs en mémoire."""

from __future__ import annotations

from collections import Counter
from threading import Lock

_lock = Lock()
_proxy_failures: Counter[str] = Counter()
_scrape_attempts: Counter[str] = Counter()
_scrape_success: Counter[str] = Counter()
_scrape_failures: Counter[str] = Counter()


def record_proxy_failure(proxy_label: str, *, reason: str = "unknown") -> None:
    key = f"{proxy_label}|{reason}"
    with _lock:
        _proxy_failures[key] += 1


def record_scrape_attempt(source: str) -> None:
    with _lock:
        _scrape_attempts[source] += 1


def record_scrape_success(source: str) -> None:
    with _lock:
        _scrape_success[source] += 1


def record_scrape_failure(source: str, *, reason: str) -> None:
    with _lock:
        _scrape_failures[f"{source}|{reason}"] += 1


def snapshot() -> dict[str, dict[str, int]]:
    with _lock:
        return {
            "proxy_failures": dict(_proxy_failures),
            "scrape_attempts": dict(_scrape_attempts),
            "scrape_success": dict(_scrape_success),
            "scrape_failures": dict(_scrape_failures),
        }


def reset_metrics() -> None:
    """Tests uniquement."""
    with _lock:
        _proxy_failures.clear()
        _scrape_attempts.clear()
        _scrape_success.clear()
        _scrape_failures.clear()
