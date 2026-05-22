"""MS-06 — Découverte dynamique et enqueue."""

from packages.discovery.service import apply_discovery_from_parse, fanout_from_recent_snapshots

__all__ = ["apply_discovery_from_parse", "fanout_from_recent_snapshots"]
