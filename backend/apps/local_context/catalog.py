"""Pays et fuseaux — Afrique d'abord (indicatif + heure locale, pas de monnaie)."""
from __future__ import annotations

COUNTRIES: list[dict[str, str]] = [
    {"code": "CD", "label": "RDC", "prefix": "+243", "tz": "Africa/Kinshasa"},
    {"code": "CG", "label": "Congo-Brazzaville", "prefix": "+242", "tz": "Africa/Lagos"},
    {"code": "CI", "label": "Côte d'Ivoire", "prefix": "+225", "tz": "Africa/Abidjan"},
    {"code": "SN", "label": "Sénégal", "prefix": "+221", "tz": "Africa/Abidjan"},
    {"code": "CM", "label": "Cameroun", "prefix": "+237", "tz": "Africa/Lagos"},
    {"code": "GA", "label": "Gabon", "prefix": "+241", "tz": "Africa/Lagos"},
    {"code": "BJ", "label": "Bénin", "prefix": "+229", "tz": "Africa/Lagos"},
    {"code": "TG", "label": "Togo", "prefix": "+228", "tz": "Africa/Abidjan"},
    {"code": "BF", "label": "Burkina Faso", "prefix": "+226", "tz": "Africa/Abidjan"},
    {"code": "ML", "label": "Mali", "prefix": "+223", "tz": "Africa/Abidjan"},
    {"code": "NE", "label": "Niger", "prefix": "+227", "tz": "Africa/Lagos"},
    {"code": "GN", "label": "Guinée", "prefix": "+224", "tz": "Africa/Abidjan"},
    {"code": "NG", "label": "Nigeria", "prefix": "+234", "tz": "Africa/Lagos"},
    {"code": "GH", "label": "Ghana", "prefix": "+233", "tz": "Africa/Accra"},
    {"code": "KE", "label": "Kenya", "prefix": "+254", "tz": "Africa/Nairobi"},
    {"code": "TZ", "label": "Tanzanie", "prefix": "+255", "tz": "Africa/Dar_es_Salaam"},
    {"code": "UG", "label": "Ouganda", "prefix": "+256", "tz": "Africa/Kampala"},
    {"code": "RW", "label": "Rwanda", "prefix": "+250", "tz": "Africa/Kigali"},
    {"code": "BI", "label": "Burundi", "prefix": "+257", "tz": "Africa/Kigali"},
    {"code": "ZA", "label": "Afrique du Sud", "prefix": "+27", "tz": "Africa/Johannesburg"},
    {"code": "MA", "label": "Maroc", "prefix": "+212", "tz": "Africa/Casablanca"},
    {"code": "TN", "label": "Tunisie", "prefix": "+216", "tz": "Africa/Tunis"},
    {"code": "DZ", "label": "Algérie", "prefix": "+213", "tz": "Africa/Algiers"},
    {"code": "EG", "label": "Égypte", "prefix": "+20", "tz": "Africa/Cairo"},
    {"code": "MG", "label": "Madagascar", "prefix": "+261", "tz": "Africa/Nairobi"},
    {"code": "MU", "label": "Maurice", "prefix": "+230", "tz": "Indian/Mauritius"},
    {"code": "OTHER", "label": "Autre", "prefix": "+", "tz": "UTC"},
]

TIMEZONES = sorted({c["tz"] for c in COUNTRIES} | {"UTC", "Africa/Lubumbashi"})


def country_defaults(code: str) -> dict[str, str]:
    for row in COUNTRIES:
        if row["code"] == code:
            return row
    return COUNTRIES[-1]
