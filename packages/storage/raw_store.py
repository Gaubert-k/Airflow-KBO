"""API publique MS-03 — put / sidecar / read bundle."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from packages.storage.config import StorageConfig, get_storage_config
from packages.storage.exceptions import (
    MetadataValidationError,
    RawBundleNotFoundError,
)
from packages.storage.hdfs_client import (
    HdfsClient,
    get_hdfs_client,
    read_json_sidecar,
    write_json_sidecar,
)
from packages.storage.models import PutResult, RawDocumentStoredEvent, StoreResult
from packages.storage.paths import (
    build_raw_dir_path,
    document_basename,
    join_hdfs_path,
    new_run_id,
)
from packages.storage.registry import on_raw_document_stored
from packages.storage.validation import reject_invalid_raw_content, validate_metadata_sidecar

logger = logging.getLogger(__name__)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_content(local_path: str | Path | bytes) -> bytes:
    if isinstance(local_path, bytes):
        return local_path
    return Path(local_path).read_bytes()


def put_raw_object(
    local_path_or_bytes: str | Path | bytes,
    hdfs_target_path: str,
    *,
    client: HdfsClient | None = None,
    validate: bool = True,
    metadata: dict[str, Any] | None = None,
    content_type: str | None = None,
) -> PutResult:
    """T03.1 — Écrit les octets bruts au chemin HDFS cible."""
    data = _load_content(local_path_or_bytes)
    if validate:
        reject_invalid_raw_content(
            data,
            metadata=metadata,
            content_type=content_type or (metadata or {}).get("content_type"),
        )
    hdfs = client or get_hdfs_client()
    hdfs.put_bytes(hdfs_target_path, data)
    digest = _sha256(data)
    return PutResult(hdfs_path=hdfs_target_path, sha256=digest, size_bytes=len(data))


def write_metadata_sidecar(
    metadata: dict[str, Any],
    hdfs_dir: str,
    *,
    client: HdfsClient | None = None,
    config: StorageConfig | None = None,
) -> str:
    """T03.2 — Écrit metadata.json dans hdfs_dir ; retourne le chemin HDFS."""
    cfg = config or get_storage_config()
    validated = validate_metadata_sidecar(metadata, schema_version=cfg.sidecar_schema_version)
    sidecar_path = join_hdfs_path(hdfs_dir, cfg.metadata_filename)
    write_json_sidecar(sidecar_path, validated, client=client)
    return sidecar_path


def read_raw_bundle(
    hdfs_dir: str,
    *,
    client: HdfsClient | None = None,
    config: StorageConfig | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """T03.3 — Lit document + metadata.json depuis hdfs_dir."""
    cfg = config or get_storage_config()
    hdfs = client or get_hdfs_client()
    meta_path = join_hdfs_path(hdfs_dir, cfg.metadata_filename)
    if not hdfs.exists(meta_path):
        raise RawBundleNotFoundError(f"metadata sidecar missing: {meta_path}")

    try:
        metadata = read_json_sidecar(meta_path, client=hdfs)
    except json.JSONDecodeError as exc:
        raise MetadataValidationError(f"invalid JSON in {meta_path}") from exc

    doc_name = metadata.get("document_name") or cfg.default_document_name
    doc_path = join_hdfs_path(hdfs_dir, doc_name)
    if not hdfs.exists(doc_path):
        alt = "document.bin" if doc_name.endswith(".html") else "document.html"
        alt_path = join_hdfs_path(hdfs_dir, alt)
        if hdfs.exists(alt_path):
            doc_path = alt_path
        else:
            raise RawBundleNotFoundError(
                f"raw document missing in {hdfs_dir} (tried {doc_name}, {alt})"
            )

    try:
        content = hdfs.get_bytes(doc_path)
    except FileNotFoundError as exc:
        raise RawBundleNotFoundError(str(exc)) from exc

    return content, metadata


def store_raw_bundle(
    *,
    source: str,
    enterprise_number: str,
    doc_type: str,
    content: bytes,
    metadata: dict[str, Any],
    run_id: str | None = None,
    document_name: str | None = None,
    client: HdfsClient | None = None,
    config: StorageConfig | None = None,
    emit_registry_event: bool = True,
) -> StoreResult:
    """
    Opération haut niveau pour MS-02 : layout + validation + sidecar + événement.
    """
    cfg = config or get_storage_config()
    resolved_run_id = run_id or new_run_id()
    hdfs_dir = build_raw_dir_path(
        cfg.hdfs_raw_root,
        source=source,
        enterprise_number=enterprise_number,
        doc_type=doc_type,
        run_id=resolved_run_id,
    )
    hdfs = client or get_hdfs_client()
    content_type = metadata.get("content_type")
    doc_name = document_name or document_basename(content_type)
    reject_invalid_raw_content(content, metadata=metadata, content_type=content_type)
    hdfs.ensure_dir(hdfs_dir)

    doc_path = join_hdfs_path(hdfs_dir, doc_name)
    put_result = put_raw_object(
        content,
        doc_path,
        client=hdfs,
        validate=False,
        metadata=metadata,
        content_type=content_type,
    )

    meta = dict(metadata)
    meta["sha256"] = put_result.sha256
    meta["document_name"] = doc_name
    meta.setdefault("schema_version", cfg.sidecar_schema_version)
    meta_path = write_metadata_sidecar(meta, hdfs_dir, client=hdfs, config=cfg)

    result = StoreResult(
        hdfs_dir=hdfs_dir,
        document_path=doc_path,
        metadata_path=meta_path,
        sha256=put_result.sha256,
        size_bytes=put_result.size_bytes,
    )

    if emit_registry_event:
        _emit_stored_event(
            enterprise_number=enterprise_number,
            source=source,
            doc_type=doc_type,
            run_id=resolved_run_id,
            result=result,
            metadata=meta,
        )

    return result


def _emit_stored_event(
    *,
    enterprise_number: str,
    source: str,
    doc_type: str,
    run_id: str,
    result: StoreResult,
    metadata: dict[str, Any],
) -> None:
    scraped_raw = metadata.get("scraped_at")
    if isinstance(scraped_raw, datetime):
        scraped_at = scraped_raw
    else:
        scraped_at = datetime.fromisoformat(str(scraped_raw).replace("Z", "+00:00"))

    event = RawDocumentStoredEvent(
        enterprise_number=enterprise_number,
        source=source,
        doc_type=doc_type,
        run_id=run_id,
        hdfs_dir=result.hdfs_dir,
        document_path=result.document_path,
        metadata_path=result.metadata_path,
        sha256=result.sha256,
        size_bytes=result.size_bytes,
        scraped_at=scraped_at,
        http_status=int(metadata["http_status"]),
        download_status=str(metadata["download_status"]),
    )
    on_raw_document_stored(event)
