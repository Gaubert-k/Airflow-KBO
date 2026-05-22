"""Tests bootstrap volume — premier démarrage uniquement."""

from __future__ import annotations

from pathlib import Path

from packages.platform.volume_bootstrap import (
    hdfs_has_scraped_documents,
    is_data_volume_uninitialized,
    mark_data_volume_initialized,
    marker_path,
)


def test_fresh_volume_when_empty(tmp_path: Path) -> None:
    (tmp_path / "data" / "hdfs-stub").mkdir(parents=True)
    assert is_data_volume_uninitialized(tmp_path) is True


def test_not_fresh_after_marker(tmp_path: Path) -> None:
    mark_data_volume_initialized({"ok": True}, repo_root=tmp_path)
    assert marker_path(tmp_path).is_file()
    assert is_data_volume_uninitialized(tmp_path) is False


def test_not_fresh_when_hdfs_has_html(tmp_path: Path) -> None:
    doc = (
        tmp_path
        / "data"
        / "hdfs-stub"
        / "raw"
        / "v1"
        / "source=kbo"
        / "enterprise_number=0123456789"
        / "doc_type=x"
        / "run_id=1"
        / "document.html"
    )
    doc.parent.mkdir(parents=True)
    doc.write_text("<html></html>", encoding="utf-8")
    assert hdfs_has_scraped_documents(tmp_path) is True
    assert is_data_volume_uninitialized(tmp_path) is False
