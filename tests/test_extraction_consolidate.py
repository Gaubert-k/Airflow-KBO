"""Tests consolidation snapshot MS-04."""

from __future__ import annotations

from packages.extraction.consolidate import consolidate_parsed_documents
from packages.extraction.parsers.generic import parse_generic_html


def test_consolidate_prefers_kbo_enterprise_detail_over_profile() -> None:
    docs = [
        {
            "source": "kbo",
            "doc_type": "profile",
            "partial": False,
            "fields": {"legal_name": "Profil court", "enterprise_number": "0203430576"},
        },
        {
            "source": "kbo",
            "doc_type": "enterprise_detail",
            "partial": False,
            "fields": {
                "legal_name": "Acme SA",
                "status_label": "Actief",
                "enterprise_number": "0203430576",
                "postal_code": "1000",
                "vat_activities": [{"code": "62.01", "label": "Programmation"}],
                "managers": [{"role": "Bestuurder", "name": "Jean Dupont"}],
            },
        },
    ]
    payload = consolidate_parsed_documents("0203430576", docs)
    detail = payload["enterprise_detail"]
    assert detail["legal_name"] == "Acme SA"
    assert detail["postal_code"] == "1000"
    assert payload["consolidation"]["kbo_doc_type"] == "enterprise_detail"


def test_consolidate_moniteur_and_bnb_auxiliary() -> None:
    bnb_fields, _, _partial = parse_generic_html(
        b"<html><head><title>Consult</title></head><body><app-root></app-root></body></html>",
        enterprise_number="0203430576",
        source="bnb",
        doc_type="consult_profile",
    )
    docs = [
        {
            "source": "kbo",
            "doc_type": "enterprise_detail",
            "partial": False,
            "fields": {"legal_name": "Test SPRL", "enterprise_number": "0203430576"},
        },
        {
            "source": "moniteur",
            "doc_type": "publication_search",
            "partial": True,
            "fields": {
                "result_link_count": 2,
                "publications_preview": ["Publication A"],
            },
        },
        {
            "source": "bnb",
            "doc_type": "consult_profile",
            "partial": True,
            "fields": bnb_fields,
        },
    ]
    payload = consolidate_parsed_documents("0203430576", docs)
    detail = payload["enterprise_detail"]
    assert detail["moniteur"]["result_link_count"] == 2
    assert len(detail["other_sources"]) == 1
    assert detail["other_sources"][0]["source"] == "bnb"
    assert "title_fragment" not in detail["other_sources"][0]
    assert "spa" in detail["other_sources"][0]["summary"].lower() or "navigateur" in detail[
        "other_sources"
    ][0]["summary"].lower()


def test_generic_parser_no_title_fragment() -> None:
    fields, _c, partial = parse_generic_html(
        b"<title>BNB</title><body><app-root></app-root></body>",
        enterprise_number="0203430576",
        source="bnb",
        doc_type="consult_profile",
    )
    assert "title_fragment" not in fields
    assert fields.get("page_title") == "BNB"
    assert partial is True
