"""Tests parseurs MS-04 (KBO NACE, Moniteur)."""

from __future__ import annotations

from pathlib import Path

from packages.extraction.parsers.kbo import parse_kbo_enterprise_detail
from packages.extraction.parsers.moniteur import parse_moniteur_publication_search

_ROOT = Path(__file__).resolve().parents[1]
_KBO_SAMPLE = (
    _ROOT
    / "data/hdfs-stub/raw/v1/source=kbo/enterprise_number=0200068636"
    / "doc_type=enterprise_detail/run_id=b359386f-c311-4555-a411-3485463b109a/document.html"
)


def test_kbo_enterprise_detail_extracts_name_and_nace() -> None:
    if not _KBO_SAMPLE.is_file():
        return
    html = _KBO_SAMPLE.read_bytes()
    fields, _candidates, partial = parse_kbo_enterprise_detail(
        html,
        enterprise_number="0200068636",
        extractor_version="test",
        schema_version=1,
    )
    assert fields["legal_name"]
    assert "Farys" in fields["legal_name"]
    assert fields["postal_code"] == "9000"
    assert len(fields["vat_activities"]) >= 1
    assert not partial


def test_moniteur_publication_search_form() -> None:
    html = b'<form name="sampleform"><input name="btw" value="0200068636"/></form>'
    fields, candidates, _partial = parse_moniteur_publication_search(
        html,
        enterprise_number="0200068636",
        doc_type="publication_search",
    )
    assert fields["enterprise_number"] == "0200068636"
    assert fields["search_form_present"] is True
    assert candidates == []
