"""Exploitation du panneau : lien lent, fuseau, coupures — pas de facturation."""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

from apps.accounts.models import User
from apps.local_context.catalog import COUNTRIES, TIMEZONES, country_defaults
from apps.local_context.models import LocalSiteProfile

WATCH_UNITS: list[dict[str, Any]] = [
    {"id": "panel", "label": "Panneau", "units": ["vzone-api"]},
    {"id": "worker", "label": "Tâches de fond", "units": ["vzone-worker"]},
    {"id": "web", "label": "Nginx (sites)", "units": ["nginx"]},
    {"id": "redis", "label": "Cache", "units": ["redis-server", "redis"]},
    {"id": "db", "label": "Base PostgreSQL", "units": ["postgresql", "postgresql@16-main", "postgres"]},
    {"id": "mail", "label": "Envoi mail", "units": ["postfix"]},
    {"id": "imap", "label": "Boîtes mail", "units": ["dovecot"]},
]


def get_profile() -> LocalSiteProfile:
    return LocalSiteProfile.get_solo()


def profile_payload() -> dict[str, Any]:
    profile = get_profile()
    return {
        "country": profile.country,
        "timezone": profile.timezone,
        "data_saver": profile.data_saver,
        "lite_panel": profile.lite_panel,
        "require_phone": profile.require_phone,
        "phone_prefix": profile.phone_prefix,
        "notify_channel": profile.notify_channel,
        "backup_window_start": profile.backup_window_start,
        "backup_window_end": profile.backup_window_end,
        "defer_heavy_jobs": profile.defer_heavy_jobs,
        "in_backup_window": in_backup_window(),
        "catalog": {
            "countries": COUNTRIES,
            "timezones": TIMEZONES,
            "notify_channels": [
                {"code": "whatsapp", "label": "WhatsApp (copier / ouvrir)"},
                {"code": "sms", "label": "SMS (copier le texte)"},
                {"code": "email", "label": "E-mail"},
            ],
        },
    }


def apply_country_defaults(profile: LocalSiteProfile, country: str) -> None:
    row = country_defaults(country)
    profile.country = row["code"]
    profile.phone_prefix = row["prefix"]
    profile.timezone = row["tz"]


def local_now() -> datetime:
    profile = get_profile()
    now = timezone.now()
    try:
        return now.astimezone(ZoneInfo(profile.timezone or "Africa/Kinshasa"))
    except ZoneInfoNotFoundError:
        return now.astimezone(ZoneInfo("UTC"))


def in_backup_window(now: datetime | None = None) -> bool:
    profile = get_profile()
    current = now or local_now()
    hour = current.hour
    start = int(profile.backup_window_start)
    end = int(profile.backup_window_end)
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def should_defer_heavy_job() -> bool:
    profile = get_profile()
    if not profile.defer_heavy_jobs:
        return False
    return not in_backup_window()


def _unit_state(names: list[str]) -> tuple[str, str]:
    if not shutil.which("systemctl"):
        return names[0], "unknown"
    last = "unknown"
    chosen = names[0]
    for name in names:
        try:
            proc = subprocess.run(
                ["systemctl", "is-active", name],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        state = (proc.stdout or "").strip() or "unknown"
        last = state
        chosen = name
        if state == "active":
            return name, "active"
        if state == "failed":
            return name, "failed"
    return chosen, last


def service_health() -> list[dict[str, str]]:
    rows = []
    for item in WATCH_UNITS:
        unit, state = _unit_state(list(item["units"]))
        rows.append({"id": item["id"], "label": item["label"], "unit": unit, "state": state})
    return rows


def overview() -> dict[str, Any]:
    profile = get_profile()
    health = service_health()
    down = sum(1 for r in health if r["state"] in {"failed", "inactive", "deactivating"})
    return {
        "data_saver": profile.data_saver,
        "lite_panel": profile.lite_panel,
        "in_backup_window": in_backup_window(),
        "timezone": profile.timezone,
        "services_down": down,
        "services": health,
    }


def compose_notice(target: User, kind: str = "welcome") -> dict[str, str]:
    """Message opérationnel à envoyer au client (site, disque, SSL) — pas une facture."""
    domain = ""
    try:
        from apps.domains.models import Domain

        domain = (
            Domain.objects.filter(owner=target, is_active=True)
            .order_by("created_at")
            .values_list("name", flat=True)
            .first()
            or ""
        )
    except Exception:  # noqa: BLE001
        domain = ""
    site = domain or target.username
    if kind == "disk":
        body = (
            f"Bonjour {target.username}, l’espace disque du compte {site} est presque plein. "
            "Supprimez des fichiers inutiles (caches, backups, mails) depuis le gestionnaire de fichiers, "
            "sinon les sites peuvent s’arrêter."
        )
    elif kind == "ssl":
        body = (
            f"Bonjour {target.username}, le certificat HTTPS de {site or 'votre site'} arrive à expiration. "
            "Connectez-vous au panneau → Domaines → SSL pour le renouveler (Let’s Encrypt)."
        )
    elif kind == "outage":
        body = (
            f"Bonjour {target.username}, le serveur a repris après une coupure. "
            f"Vérifiez {site or 'votre site'} ; s’il ne répond pas, réessayez dans quelques minutes."
        )
    else:
        body = (
            f"Bonjour {target.username}, le compte {site} est prêt. "
            "Ouvrez le panneau pour les fichiers, e-mails et le site. "
            "En cas de connexion lente, le mode économie de données réduit la conso mobile."
        )
    phone = (target.phone or "").replace(" ", "")
    digits = "".join(ch for ch in phone if ch.isdigit())
    wa = f"https://wa.me/{digits}?text={quote(body)}" if digits else ""
    sms = f"sms:{phone}?body={quote(body)}" if phone else ""
    return {"body": body, "whatsapp_url": wa, "sms_url": sms, "phone": target.phone or ""}
