"""MS-03 — Stockage brut HDFS (layout, sidecar, intégrité)."""

from packages.storage.exceptions import (
    HdfsConnectionError,
    HdfsPermissionError,
    HdfsQuotaError,
    InvalidRawContentError,
    MetadataValidationError,
    RawBundleNotFoundError,
    StorageError,
)
from packages.storage.models import PutResult, RawDocumentStoredEvent, StoreResult
from packages.storage.raw_store import (
    build_raw_dir_path,
    put_raw_object,
    read_raw_bundle,
    store_raw_bundle,
    write_metadata_sidecar,
)
from packages.storage.registry import on_raw_document_stored, register_raw_document_listener

__all__ = [
    "HdfsConnectionError",
    "HdfsPermissionError",
    "HdfsQuotaError",
    "InvalidRawContentError",
    "MetadataValidationError",
    "PutResult",
    "RawBundleNotFoundError",
    "RawDocumentStoredEvent",
    "StorageError",
    "StoreResult",
    "build_raw_dir_path",
    "on_raw_document_stored",
    "put_raw_object",
    "read_raw_bundle",
    "register_raw_document_listener",
    "store_raw_bundle",
    "write_metadata_sidecar",
]
