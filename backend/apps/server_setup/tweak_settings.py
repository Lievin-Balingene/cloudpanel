"""Catalogue Tweak Settings (WHM-like) — paramètres globaux du panneau."""
from __future__ import annotations

from typing import Any

# type: bool | int | str | choice
TWEAK_CATALOG: list[dict[str, Any]] = [
    {
        "id": "security",
        "label": "Security",
        "settings": [
            {
                "key": "require_strong_passwords",
                "label": "Exiger des mots de passe forts",
                "type": "bool",
                "default": True,
                "help": "Refuse les mots de passe faibles à la création de comptes.",
            },
            {
                "key": "min_password_length",
                "label": "Longueur minimale du mot de passe",
                "type": "int",
                "default": 10,
                "min": 8,
                "max": 128,
            },
            {
                "key": "enable_2fa_prompt",
                "label": "Proposer la 2FA aux admins",
                "type": "bool",
                "default": True,
            },
            {
                "key": "lockout_after_failures",
                "label": "Verrouillage après échecs de connexion",
                "type": "int",
                "default": 5,
                "min": 0,
                "max": 50,
                "help": "0 = désactivé.",
            },
            {
                "key": "session_idle_minutes",
                "label": "Expiration session inactive (min)",
                "type": "int",
                "default": 60,
                "min": 5,
                "max": 1440,
            },
            {
                "key": "smtp_restrictions",
                "label": "SMTP Restrictions",
                "type": "bool",
                "default": False,
                "help": (
                    "Empêche les utilisateurs de by-passer le serveur mail pour envoyer "
                    "(seuls root, MTA et mailman peuvent joindre des SMTP distants sur le port 25). "
                    "Aussi disponible dans Security Center → SMTP Restrictions."
                ),
            },
        ],
    },
    {
        "id": "accounts",
        "label": "Accounts",
        "settings": [
            {
                "key": "allow_shell_by_default",
                "label": "Shell jailed par défaut pour nouveaux comptes",
                "type": "bool",
                "default": False,
            },
            {
                "key": "max_accounts_per_reseller",
                "label": "Limite comptes par revendeur (0 = illimité / pas de plafond global)",
                "type": "int",
                "default": 0,
                "min": 0,
                "max": 100000,
                "help": "Plafond serveur pour tous les revendeurs. 0 = aucun plafond global (la limite vient du package / ACL).",
            },
            {
                "key": "auto_create_dns_zone",
                "label": "Créer automatiquement la zone DNS",
                "type": "bool",
                "default": True,
            },
            {
                "key": "default_quota_mb",
                "label": "Quota disque par défaut (Mo)",
                "type": "int",
                "default": 10240,
                "min": 100,
                "max": 1048576,
            },
        ],
    },
    {
        "id": "email",
        "label": "Email",
        "settings": [
            {
                "key": "enable_catch_all",
                "label": "Autoriser catch-all",
                "type": "bool",
                "default": True,
            },
            {
                "key": "max_mailbox_mb",
                "label": "Taille max boîte mail par défaut (Mo)",
                "type": "int",
                "default": 1024,
                "min": 10,
                "max": 102400,
            },
            {
                "key": "require_spf_on_create",
                "label": "Ajouter SPF à la création de domaine",
                "type": "bool",
                "default": True,
            },
            {
                "key": "require_dkim_on_create",
                "label": "Activer DKIM à la création",
                "type": "bool",
                "default": True,
            },
        ],
    },
    {
        "id": "dns",
        "label": "DNS",
        "settings": [
            {
                "key": "default_ttl",
                "label": "TTL DNS par défaut",
                "type": "int",
                "default": 14400,
                "min": 60,
                "max": 86400,
            },
            {
                "key": "allow_dnssec",
                "label": "Autoriser DNSSEC",
                "type": "bool",
                "default": True,
            },
        ],
    },
    {
        "id": "php",
        "label": "PHP",
        "settings": [
            {
                "key": "default_php_version",
                "label": "Version PHP par défaut",
                "type": "choice",
                "default": "8.2",
                "choices": ["7.4", "8.0", "8.1", "8.2", "8.3", "8.4"],
            },
            {
                "key": "allow_ini_edit",
                "label": "Autoriser l'édition php.ini côté client",
                "type": "bool",
                "default": True,
            },
            {
                "key": "display_errors_default",
                "label": "display_errors par défaut",
                "type": "bool",
                "default": False,
            },
        ],
    },
    {
        "id": "backups",
        "label": "Backups",
        "settings": [
            {
                "key": "daily_backup_enabled",
                "label": "Sauvegarde quotidienne",
                "type": "bool",
                "default": True,
            },
            {
                "key": "backup_retention_days",
                "label": "Rétention (jours)",
                "type": "int",
                "default": 14,
                "min": 1,
                "max": 365,
            },
            {
                "key": "backup_notify_email",
                "label": "Notifier les échecs de backup",
                "type": "bool",
                "default": True,
            },
        ],
    },
    {
        "id": "logging",
        "label": "Logging",
        "settings": [
            {
                "key": "retain_access_logs_days",
                "label": "Rétention logs d'accès (jours)",
                "type": "int",
                "default": 30,
                "min": 1,
                "max": 365,
            },
            {
                "key": "log_ai_actions",
                "label": "Journaliser les actions IA",
                "type": "bool",
                "default": True,
            },
        ],
    },
    {
        "id": "ui",
        "label": "UI",
        "settings": [
            {
                "key": "panel_locale",
                "label": "Langue du panneau",
                "type": "choice",
                "default": "fr",
                "choices": ["fr", "en"],
            },
            {
                "key": "show_ai_assistant",
                "label": "Afficher l'assistant IA",
                "type": "bool",
                "default": True,
            },
            {
                "key": "compact_home_buttons",
                "label": "Boutons d'accueil compacts",
                "type": "bool",
                "default": True,
            },
        ],
    },
    {
        "id": "performance",
        "label": "Performance",
        "settings": [
            {
                "key": "enable_http2",
                "label": "HTTP/2",
                "type": "bool",
                "default": True,
            },
            {
                "key": "gzip_compression",
                "label": "Compression gzip",
                "type": "bool",
                "default": True,
            },
            {
                "key": "php_opcache",
                "label": "OPcache PHP",
                "type": "bool",
                "default": True,
            },
        ],
    },
    {
        "id": "notifications",
        "label": "Notifications",
        "settings": [
            {
                "key": "notify_disk_warn_pct",
                "label": "Alerte disque à (%)",
                "type": "int",
                "default": 85,
                "min": 50,
                "max": 99,
            },
            {
                "key": "notify_ssl_expiry_days",
                "label": "Alerte SSL avant expiration (jours)",
                "type": "int",
                "default": 14,
                "min": 1,
                "max": 90,
            },
            {
                "key": "notify_service_down",
                "label": "Notifier si un service tombe",
                "type": "bool",
                "default": True,
            },
        ],
    },
]


def catalog_defaults() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cat in TWEAK_CATALOG:
        for s in cat["settings"]:
            out[s["key"]] = s["default"]
    return out


def merge_tweaks(stored: dict[str, Any] | None) -> dict[str, Any]:
    merged = catalog_defaults()
    if stored:
        for k, v in stored.items():
            if k in merged:
                merged[k] = v
    return merged


def validate_tweaks(incoming: dict[str, Any]) -> dict[str, Any]:
    """Valide et ne garde que les clés connues."""
    meta_by_key = {
        s["key"]: s for cat in TWEAK_CATALOG for s in cat["settings"]
    }
    cleaned: dict[str, Any] = {}
    for key, value in (incoming or {}).items():
        meta = meta_by_key.get(key)
        if not meta:
            continue
        t = meta["type"]
        if t == "bool":
            cleaned[key] = bool(value)
        elif t == "int":
            try:
                n = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key}: entier requis") from exc
            lo = meta.get("min")
            hi = meta.get("max")
            if lo is not None and n < lo:
                n = lo
            if hi is not None and n > hi:
                n = hi
            cleaned[key] = n
        elif t == "choice":
            choices = meta.get("choices") or []
            s = str(value)
            if s not in choices:
                raise ValueError(f"{key}: valeur non autorisée")
            cleaned[key] = s
        else:
            cleaned[key] = str(value)
    return cleaned


def tweak_payload(stored: dict[str, Any] | None) -> dict[str, Any]:
    values = merge_tweaks(stored)
    return {
        "categories": TWEAK_CATALOG,
        "values": values,
    }


def get_tweaks() -> dict[str, Any]:
    """Valeurs merge (defaults + JSON ServerSetup) — toujours à jour."""
    try:
        from apps.server_setup.models import ServerSetup

        return merge_tweaks(ServerSetup.get_solo().tweak_settings)
    except Exception:  # noqa: BLE001
        return catalog_defaults()


def get_tweak(key: str, default: Any = None) -> Any:
    tweaks = get_tweaks()
    if key in tweaks:
        return tweaks[key]
    return default


# Clés exposées à tout utilisateur authentifié (effet UI / session)
PUBLIC_TWEAK_KEYS = frozenset(
    {
        "panel_locale",
        "show_ai_assistant",
        "compact_home_buttons",
        "session_idle_minutes",
        "enable_2fa_prompt",
        "require_strong_passwords",
        "min_password_length",
        "allow_ini_edit",
    }
)


def public_tweaks_payload() -> dict[str, Any]:
    values = get_tweaks()
    return {k: values[k] for k in PUBLIC_TWEAK_KEYS if k in values}


def apply_tweak_side_effects(
    previous: dict[str, Any],
    cleaned: dict[str, Any],
) -> list[str]:
    """
    Applique les effets réels des tweaks modifiés.
    Retourne la liste des effets appliqués (pour l'UI).
    """
    applied: list[str] = []
    merged = dict(previous)
    merged.update(cleaned)

    # --- Security → SecurityPolicy ---
    sec_keys = {
        "min_password_length",
        "require_strong_passwords",
        "lockout_after_failures",
        "enable_2fa_prompt",
    }
    if sec_keys & set(cleaned.keys()):
        try:
            from apps.security.services import get_policy, update_policy

            policy = get_policy()
            kwargs: dict[str, Any] = {}
            if "min_password_length" in cleaned:
                kwargs["password_min_length"] = int(cleaned["min_password_length"])
            if "require_strong_passwords" in cleaned:
                strong = bool(cleaned["require_strong_passwords"])
                kwargs["require_uppercase"] = strong
                kwargs["require_digit"] = strong
                kwargs["require_special"] = strong
            if "lockout_after_failures" in cleaned:
                n = int(cleaned["lockout_after_failures"])
                # 0 = désactivé → très haut plafond
                kwargs["lockout_max_attempts"] = 999 if n == 0 else n
            if "enable_2fa_prompt" in cleaned:
                # Prompt ≠ force ; on mappe force_2fa_admins seulement si déjà forcé ailleurs
                # Ici on stocke le prompt côté public tweaks ; pas de force hard.
                pass
            if kwargs:
                update_policy(**kwargs)
                applied.append("security_policy")
            del policy
        except Exception:  # noqa: BLE001
            pass

    # --- SMTP ---
    if "smtp_restrictions" in cleaned and cleaned["smtp_restrictions"] != previous.get(
        "smtp_restrictions"
    ):
        try:
            from apps.security.smtp_restrictions import apply_from_tweak

            apply_from_tweak(bool(cleaned["smtp_restrictions"]))
            applied.append("smtp_restrictions")
        except Exception:  # noqa: BLE001
            pass

    # --- Performance hints (nginx/OLS flags stockés ; apply soft) ---
    perf_keys = {"enable_http2", "gzip_compression", "php_opcache"}
    if perf_keys & set(cleaned.keys()):
        try:
            from apps.domains.services import refresh_web_routing

            refresh_web_routing()
            applied.append("web_routing_refresh")
        except Exception:  # noqa: BLE001
            pass

    # --- PHP default version ---
    if "default_php_version" in cleaned:
        try:
            from apps.php.models import PhpVersion
            from apps.php.services import ensure_default_versions, set_default_version

            ensure_default_versions()
            ver = PhpVersion.objects.filter(
                version=str(cleaned["default_php_version"]),
                is_available=True,
            ).first()
            if ver:
                set_default_version(ver.pk)
                applied.append("php_default_version")
        except Exception:  # noqa: BLE001
            pass

    # --- Monitoring notification thresholds ---
    notify_keys = {"notify_disk_warn_pct", "notify_service_down", "notify_ssl_expiry_days"}
    if notify_keys & set(cleaned.keys()):
        try:
            from apps.monitoring.services import sync_tweak_alert_rules

            sync_tweak_alert_rules(merged)
            applied.append("monitoring_alerts")
        except Exception:  # noqa: BLE001
            pass

    # UI / locale / AI : appliqués côté frontend via public endpoint (pas de side-effect serveur)
    ui_keys = {"panel_locale", "show_ai_assistant", "compact_home_buttons", "session_idle_minutes"}
    if ui_keys & set(cleaned.keys()):
        applied.append("ui_settings")

    if "max_accounts_per_reseller" in cleaned:
        applied.append("reseller_account_limit")

    if "default_quota_mb" in cleaned or "allow_shell_by_default" in cleaned:
        applied.append("account_defaults")

    if "log_ai_actions" in cleaned:
        applied.append("ai_logging")

    if any(
        k in cleaned
        for k in (
            "default_ttl",
            "auto_create_dns_zone",
            "require_spf_on_create",
            "require_dkim_on_create",
            "allow_ini_edit",
            "display_errors_default",
            "max_mailbox_mb",
            "enable_catch_all",
            "daily_backup_enabled",
            "backup_retention_days",
            "backup_notify_email",
            "allow_dnssec",
            "retain_access_logs_days",
        )
    ):
        applied.append("provisioning_defaults")

    return applied
