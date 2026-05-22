"""Conventions de chemins HDFS raw/v1 (contrat gelé MS-03)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

_ENTERPRISE_RE = re.compile(r"^\d{10}$")
_SAFE_SEGMENT = re.compile(r"^[a-zA-Z0-9_.-]+$")


@dataclass(frozen=True)
class RawPathKey:
    source: str
    enterprise_number: str
    doc_type: str
    run_id: str


def normalize_enterprise_number(value: str) -> str:
    """10 chiffres (supprime BE, espaces, points)."""
    digits = re.sub(r"\D", "", value)
    if len(digits) != 10:
        msg = f"enterprise_number must be 10 digits, got {value!r}"
        raise ValueError(msg)
    return digits


def _check_segment(name: str, value: str) -> str:
    if not _SAFE_SEGMENT.match(value):
        msg = f"{name} contains invalid characters: {value!r}"
        raise ValueError(msg)
    return value


def new_run_id() -> str:
    return str(uuid.uuid4())


def build_raw_dir_path(
    raw_root: str,
    *,
    source: str,
    enterprise_number: str,
    doc_type: str,
    run_id: str | None = None,
) -> str:
    """
    Construit le répertoire HDFS d'un objet brut.

    Layout: ``{raw_root}/source={source}/enterprise_number={NN}/doc_type={type}/run_id={uuid}/``
    """
    ent = normalize_enterprise_number(enterprise_number)
    src = _check_segment("source", source)
    dtype = _check_segment("doc_type", doc_type)
    rid = _check_segment("run_id", run_id or new_run_id())
    return (
        f"{raw_root.rstrip('/')}/source={src}/enterprise_number={ent}"
        f"/doc_type={dtype}/run_id={rid}"
    )


def document_basename(content_type: str | None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if content_type and "html" in content_type.lower():
        return "document.html"
    return "document.bin"


def join_hdfs_path(directory: str, filename: str) -> str:
    return f"{directory.rstrip('/')}/{filename}"
