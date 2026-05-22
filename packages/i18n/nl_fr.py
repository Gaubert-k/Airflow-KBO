"""
Mapping pragmatique néerlandais → français pour l'affichage dashboard.

Les nouvelles acquisitions KBO/Moniteur utilisent ``lang=fr`` / ``language=fr`` ;
ce module normalise les snapshots et HTML stub encore en NL.
"""

from __future__ import annotations

import re
from typing import Any

# Correspondances exactes (libellés KBO / NACE courants dans le jeu de données TP).
_EXACT_NL_FR: dict[str, str] = {
    # Statut
    "Actief": "Actif",
    "Inactief": "Inactif",
    "Stopgezet": "Radié",
    "Gesloten": "Clôturé",
    # Rôles dirigeants
    "Bestuurder": "Administrateur",
    "Zaakvoerder": "Gérant",
    "Voorzitter": "Président",
    "Commissaris": "Commissaire",
    "Burgemeester": "Bourgmestre",
    "Persoon belast met dagelijks bestuur": "Personne chargée de la gestion journalière",
    # Formes juridiques
    "Stad / gemeente": "Ville / commune",
    "Dienstverlenende vereniging (Vlaams Gewest)": (
        "Association prestataire de services (Région flamande)"
    ),
    "Opdrachthoudende vereniging (Vlaams Gewest)": (
        "Association gestionnaire de mission (Région flamande)"
    ),
    "Naamloze vennootschap": "Société anonyme",
    "Naamloze vennootschap van publiek recht": "Société anonyme de droit public",
    "Besloten vennootschap": "Société à responsabilité limitée",
    "Besloten vennootschap met beperkte aansprakelijkheid": (
        "Société à responsabilité limitée"
    ),
    "Vereniging zonder winstoogmerk": "Association sans but lucratif",
    "Coöperatieve vennootschap": "Société coopérative",
    "Coöperatieve vennootschap met beperkte aansprakelijkheid": (
        "Société coopérative à responsabilité limitée"
    ),
    "Eenmanszaak": "Entreprise individuelle",
    "Vennootschap onder firma": "Société en nom collectif",
    "Commanditaire vennootschap": "Société en commandite",
    "Vennootschap onder firma met twee vennootschappen": (
        "Société en nom collectif entre personnes morales"
    ),
    "Instelling van openbaar nut": "Établissement d'utilité publique",
    "Buitenlandse onderneming": "Entreprise étrangère",
    "Europees economisch samenwerkingsverband": "Groupement européen d'intérêt économique",
    # Activités NACE (échantillons fréquents)
    "Activiteiten van watersportclubs": "Activités des clubs nautiques",
    "Exploitatie van sportaccommodaties": "Exploitation d'installations sportives",
    "Gemeentelijke overheid, met uitzondering van het OCMW": (
        "Administration communale, à l'exception du CPAS"
    ),
    "Productie en distributie van elektriciteit": "Production et distribution d'électricité",
    "Distributie van gas": "Distribution de gaz",
    "Winning en distributie van water": "Captage, traitement et distribution d'eau",
    "Afvalwaterafvoer": "Collecte et traitement des eaux usées",
    "Algemene openbare diensten": "Services publics généraux",
    "Exploitatie van bossen": "Exploitation forestière",
    "Groothandel in hout": "Commerce de gros de bois",
    "Openbare Centra voor Maatschappelijk Welzijn (OCMW)": (
        "Centres publics d'action sociale (CPAS)"
    ),
    "Openbaar bestuur op het gebied van het bedrijfsleven; stimuleren van het bedrijfsleven": (
        "Administration publique économique ; promotion de l'entreprise"
    ),
    "Verhuur en exploitatie van eigen of geleased niet-residentieel onroerend goed, exclusief terreinen": (
        "Location et exploitation de biens immobiliers non résidentiels (hors terrains)"
    ),
    "Bosbouw en bosbouwactiviteiten": "Sylviculture et activités forestières",
    "Overige persoonlijke diensten": "Autres services personnels",
    "Verplichte sociale verzekeringen, met uitzondering van ziekenfondsen": (
        "Assurances sociales obligatoires (hors mutualités)"
    ),
    "Cafés en bars": "Cafés et bars",
}

# Remplacements partiels (ordre : plus long d'abord).
_PARTIAL_NL_FR: list[tuple[str, str]] = [
    ("Vlaams Gewest", "Région flamande"),
    ("Waals Gewest", "Région wallonne"),
    ("Brussels Hoofdstedelijk Gewest", "Région de Bruxelles-Capitale"),
    ("vennootschap", "société"),
    ("vereniging", "association"),
    ("gemeente", "commune"),
]


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def translate_nl_to_fr(value: str | None) -> str | None:
    """Traduit une chaîne NL connue ; laisse inchangé si déjà FR ou inconnu."""
    if value is None:
        return None
    text = _normalize_key(value)
    if not text:
        return value
    if text in _EXACT_NL_FR:
        return _EXACT_NL_FR[text]
    lowered = text.casefold()
    for nl, fr in _EXACT_NL_FR.items():
        if nl.casefold() == lowered:
            return fr
    out = text
    for nl_part, fr_part in _PARTIAL_NL_FR:
        if nl_part.casefold() in out.casefold():
            out = re.sub(re.escape(nl_part), fr_part, out, flags=re.IGNORECASE)
    return out if out != text else value


def translate_snapshot_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Francise les champs métier d'un bloc ``enterprise_detail`` ou champs KBO."""
    if not fields:
        return fields
    out = dict(fields)
    for key in ("status_label", "legal_form", "financial_notes"):
        if isinstance(out.get(key), str):
            translated = translate_nl_to_fr(out[key])
            if translated is not None:
                out[key] = translated
    managers = out.get("managers")
    if isinstance(managers, list):
        out["managers"] = [
            {
                **row,
                "role": translate_nl_to_fr(row.get("role")) if row.get("role") else row.get("role"),
                "name": row.get("name"),
            }
            for row in managers
            if isinstance(row, dict)
        ]
    activities = out.get("vat_activities")
    if isinstance(activities, list):
        out["vat_activities"] = [
            {
                **row,
                "code": row.get("code"),
                "label": translate_nl_to_fr(row.get("label"))
                if row.get("label")
                else row.get("label"),
            }
            for row in activities
            if isinstance(row, dict)
        ]
    return out
