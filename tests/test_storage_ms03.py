"""Tests MS-03 — stockage HDFS (stub local) round-trip et validation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from packages.storage.config import StorageConfig
from packages.storage.exceptions import InvalidRawContentError, RawBundleNotFoundError
from packages.storage.hdfs_client import LocalFilesystemHdfsClient
from packages.storage.models import RawDocumentStoredEvent
from packages.storage.paths import build_raw_dir_path, normalize_enterprise_number
from packages.storage.raw_store import (
    put_raw_object,
    read_raw_bundle,
    store_raw_bundle,
    write_metadata_sidecar,
)
from packages.storage.registry import clear_raw_document_listeners, register_raw_document_listener


def _sample_metadata() -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "scraped_at": now,
        "source": "kbo",
        "download_status": "SUCCESS",
        "http_status": 200,
        "proxy_or_ip": "direct",
        "attempt_count": 1,
        "last_updated_at": now,
        "content_type": "text/html",
        "url": "https://example.test/enterprise",
        "doc_type": "profile",
    }


def _sample_html() -> bytes:
    return (
        b"<!DOCTYPE html><html><head><title>Enterprise BE0123456789</title></head>"
        b"<body><p>Valid KBO-like page with enough content for storage boundary.</p></body></html>"
    )


@pytest.fixture
def storage_config(tmp_path: Path) -> StorageConfig:
    return StorageConfig(
        hdfs_raw_root="hdfs://localhost:9000/raw/v1",
        hdfs_local_root=tmp_path / "hdfs-stub",
    )


@pytest.fixture
def hdfs_client(storage_config: StorageConfig) -> LocalFilesystemHdfsClient:
    return LocalFilesystemHdfsClient(storage_config)


@pytest.fixture(autouse=True)
def _clear_listeners() -> None:
    clear_raw_document_listeners()
    yield
    clear_raw_document_listeners()


def test_normalize_enterprise_number() -> None:
    assert normalize_enterprise_number("BE 0123.456.789") == "0123456789"


def test_build_raw_dir_path_layout(storage_config: StorageConfig) -> None:
    path = build_raw_dir_path(
        storage_config.hdfs_raw_root,
        source="kbo",
        enterprise_number="0123456789",
        doc_type="profile",
        run_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    assert path == (
        "hdfs://localhost:9000/raw/v1/source=kbo/enterprise_number=0123456789"
        "/doc_type=profile/run_id=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    )


def test_roundtrip_bit_identical(
    hdfs_client: LocalFilesystemHdfsClient,
    storage_config: StorageConfig,
) -> None:
    run_id = "test-run-001"
    html = _sample_html()
    meta = _sample_metadata()

    result = store_raw_bundle(
        source="kbo",
        enterprise_number="0123456789",
        doc_type="profile",
        content=html,
        metadata=meta,
        run_id=run_id,
        client=hdfs_client,
        config=storage_config,
        emit_registry_event=False,
    )

    loaded, sidecar = read_raw_bundle(result.hdfs_dir, client=hdfs_client, config=storage_config)

    assert loaded == html
    assert sidecar["sha256"] == result.sha256
    assert sidecar["download_status"] == "SUCCESS"
    assert sidecar["schema_version"] == 1

    local_doc = hdfs_client.resolve_local(result.document_path)
    assert local_doc.read_bytes() == html


def test_put_raw_object_from_bytes(
    hdfs_client: LocalFilesystemHdfsClient,
    storage_config: StorageConfig,
) -> None:
    hdfs_dir = build_raw_dir_path(
        storage_config.hdfs_raw_root,
        source="kbo",
        enterprise_number="0123456789",
        doc_type="profile",
        run_id="put-bytes",
    )
    doc_path = f"{hdfs_dir}/document.html"
    meta = _sample_metadata()
    content = _sample_html()

    put_result = put_raw_object(
        content,
        doc_path,
        client=hdfs_client,
        metadata=meta,
        content_type="text/html",
    )
    write_metadata_sidecar(
        {**meta, "sha256": put_result.sha256, "document_name": "document.html"},
        hdfs_dir,
        client=hdfs_client,
        config=storage_config,
    )

    loaded, _ = read_raw_bundle(hdfs_dir, client=hdfs_client, config=storage_config)
    assert loaded == content
    assert put_result.size_bytes == len(content)


def test_rejects_error_page_html(
    hdfs_client: LocalFilesystemHdfsClient,
    storage_config: StorageConfig,
) -> None:
    bad_html = b"<!DOCTYPE html><html><head><title>404 Not Found</title></head><body></body></html>"
    meta = _sample_metadata()

    with pytest.raises(InvalidRawContentError, match="error marker"):
        store_raw_bundle(
            source="kbo",
            enterprise_number="0123456789",
            doc_type="profile",
            content=bad_html,
            metadata=meta,
            run_id="err-page",
            client=hdfs_client,
            config=storage_config,
            emit_registry_event=False,
        )


def test_rejects_failed_http_status() -> None:
    meta = {**_sample_metadata(), "http_status": 404}
    with pytest.raises(InvalidRawContentError, match="http_status"):
        store_raw_bundle(
            source="kbo",
            enterprise_number="0123456789",
            doc_type="profile",
            content=_sample_html(),
            metadata=meta,
            run_id="http-404",
            emit_registry_event=False,
        )


def test_registry_event_emitted(
    hdfs_client: LocalFilesystemHdfsClient,
    storage_config: StorageConfig,
) -> None:
    events: list[RawDocumentStoredEvent] = []
    register_raw_document_listener(events.append)

    store_raw_bundle(
        source="kbo",
        enterprise_number="0123456789",
        doc_type="profile",
        content=_sample_html(),
        metadata=_sample_metadata(),
        run_id="evt-001",
        client=hdfs_client,
        config=storage_config,
    )

    assert len(events) == 1
    assert events[0].enterprise_number == "0123456789"
    assert events[0].sha256
    assert events[0].run_id == "evt-001"


def test_missing_bundle_raises(
    hdfs_client: LocalFilesystemHdfsClient,
    storage_config: StorageConfig,
) -> None:
    missing = build_raw_dir_path(
        storage_config.hdfs_raw_root,
        source="kbo",
        enterprise_number="0123456789",
        doc_type="profile",
        run_id="missing",
    )
    with pytest.raises(RawBundleNotFoundError):
        read_raw_bundle(missing, client=hdfs_client, config=storage_config)
