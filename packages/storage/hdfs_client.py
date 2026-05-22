"""Client HDFS — stub filesystem local pour dev/CI (contrat URI hdfs://)."""

from __future__ import annotations

import errno
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urlparse

from packages.storage.config import StorageConfig, get_storage_config
from packages.storage.exceptions import (
    HdfsConnectionError,
    HdfsPermissionError,
    HdfsQuotaError,
)

logger = logging.getLogger(__name__)


class HdfsClient(ABC):
    @abstractmethod
    def put_bytes(self, hdfs_path: str, data: bytes) -> None: ...

    @abstractmethod
    def get_bytes(self, hdfs_path: str) -> bytes: ...

    @abstractmethod
    def exists(self, hdfs_path: str) -> bool: ...

    @abstractmethod
    def ensure_dir(self, hdfs_dir: str) -> None: ...


class LocalFilesystemHdfsClient(HdfsClient):
    """
    Mappe les URI ``hdfs://host:port/...`` vers ``HDFS_LOCAL_ROOT/...``.

    Équivalent cours-approuvé pour développement local sans cluster Hadoop.
    """

    def __init__(self, config: StorageConfig | None = None) -> None:
        self._config = config or get_storage_config()
        self._local_root = self._config.hdfs_local_root
        self._uri_prefix = self._hdfs_authority_prefix()

    def _hdfs_authority_prefix(self) -> str:
        parsed = urlparse(self._config.hdfs_raw_root)
        if parsed.scheme != "hdfs":
            msg = f"HDFS_RAW_ROOT must use hdfs:// scheme, got {self._config.hdfs_raw_root!r}"
            raise ValueError(msg)
        netloc = parsed.netloc or "localhost:9000"
        return f"hdfs://{netloc}"

    def resolve_local(self, hdfs_path: str) -> Path:
        if hdfs_path.startswith(self._uri_prefix):
            rel = hdfs_path[len(self._uri_prefix) :].lstrip("/")
        elif hdfs_path.startswith("hdfs://"):
            parsed = urlparse(hdfs_path)
            rel = parsed.path.lstrip("/")
        else:
            rel = hdfs_path.lstrip("/")
        local = (self._local_root / rel).resolve()
        root_resolved = self._local_root.resolve()
        try:
            local.relative_to(root_resolved)
        except ValueError as exc:
            raise HdfsPermissionError(f"path escapes HDFS_LOCAL_ROOT: {hdfs_path}") from exc
        return local

    def to_hdfs_uri(self, local_relative: str) -> str:
        rel = local_relative.lstrip("/")
        return f"{self._uri_prefix}/{rel}"

    def ensure_dir(self, hdfs_dir: str) -> None:
        path = self.resolve_local(hdfs_dir)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._raise_actionable(hdfs_dir, exc)

    def put_bytes(self, hdfs_path: str, data: bytes) -> None:
        path = self.resolve_local(hdfs_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            self._raise_actionable(hdfs_path, exc)
        logger.debug("HDFS écriture %s (%d octets)", hdfs_path, len(data))

    def get_bytes(self, hdfs_path: str) -> bytes:
        path = self.resolve_local(hdfs_path)
        if not path.is_file():
            raise FileNotFoundError(hdfs_path)
        try:
            return path.read_bytes()
        except OSError as exc:
            self._raise_actionable(hdfs_path, exc)

    def exists(self, hdfs_path: str) -> bool:
        return self.resolve_local(hdfs_path).exists()

    @staticmethod
    def _raise_actionable(hdfs_path: str, exc: OSError) -> None:
        if exc.errno in (errno.EACCES, errno.EPERM):
            raise HdfsPermissionError(f"permission denied for {hdfs_path}") from exc
        if exc.errno in (errno.ENOSPC, errno.EDQUOT):
            raise HdfsQuotaError(f"quota or disk full for {hdfs_path}") from exc
        if exc.errno in (errno.ECONNREFUSED, errno.ENETUNREACH, errno.EHOSTUNREACH):
            raise HdfsConnectionError(f"cannot reach storage backend for {hdfs_path}") from exc
        raise HdfsConnectionError(f"storage I/O failed for {hdfs_path}: {exc}") from exc


def get_hdfs_client(config: StorageConfig | None = None) -> HdfsClient:
    return LocalFilesystemHdfsClient(config)


def write_json_sidecar(hdfs_path: str, payload: dict, client: HdfsClient | None = None) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    (client or get_hdfs_client()).put_bytes(hdfs_path, data)


def read_json_sidecar(hdfs_path: str, client: HdfsClient | None = None) -> dict:
    raw = (client or get_hdfs_client()).get_bytes(hdfs_path)
    return json.loads(raw.decode("utf-8"))
