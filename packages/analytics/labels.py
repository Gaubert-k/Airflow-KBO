"""Libellés français pour l'affichage MS-08."""

from __future__ import annotations

BUSINESS_STATUS_FR: dict[str, str] = {
    "ACTIVE": "Actif",
    "INACTIVE": "Inactif",
    "STRUCK_OFF": "Radié / cessé",
    "MERGED": "Fusionné",
    "UNKNOWN": "Non déterminé",
}


def business_status_label(code: str) -> str:
    return BUSINESS_STATUS_FR.get(code, code.replace("_", " ").title())


def format_nace_code(code: str) -> str:
    """Affiche un code NACE belge lisible (ex. 84114 → 84.11.4 si 5 chiffres)."""
    digits = "".join(c for c in code if c.isdigit())
    if len(digits) == 5:
        return f"{digits[:2]}.{digits[2:4]}.{digits[4]}"
    if len(digits) == 4:
        return f"{digits[:2]}.{digits[2:]}"
    return code
