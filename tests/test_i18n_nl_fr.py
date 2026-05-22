"""Tests francisation NL → FR (dashboard / snapshots)."""

from __future__ import annotations

from packages.i18n.nl_fr import translate_nl_to_fr, translate_snapshot_fields


def test_translate_status_and_role() -> None:
    assert translate_nl_to_fr("Actief") == "Actif"
    assert translate_nl_to_fr("Bestuurder") == "Administrateur"


def test_translate_legal_form_dienstverlenende() -> None:
    assert translate_nl_to_fr("Dienstverlenende vereniging (Vlaams Gewest)") == (
        "Association prestataire de services (Région flamande)"
    )


def test_translate_snapshot_fields_full() -> None:
    detail = {
        "status_label": "Actief",
        "legal_form": "Naamloze vennootschap",
        "managers": [{"role": "Bestuurder", "name": "Dupont"}],
        "vat_activities": [
            {"code": "93.126", "label": "Activiteiten van watersportclubs"},
        ],
    }
    out = translate_snapshot_fields(detail)
    assert out["status_label"] == "Actif"
    assert out["legal_form"] == "Société anonyme"
    assert out["managers"][0]["role"] == "Administrateur"
    assert "clubs nautiques" in out["vat_activities"][0]["label"]


def test_translate_leaves_french_unchanged() -> None:
    assert translate_nl_to_fr("Actif") == "Actif"
    assert translate_nl_to_fr("Administrateur") == "Administrateur"
