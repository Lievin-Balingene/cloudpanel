"""Tools compte / dashboard / package / sécurité (lecture)."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import ok, run_service


@register_tool(
    name="get_account_overview",
    description="Vue d'ensemble du compte client (disque, compteurs ressources, infos).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def get_account_overview(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params

    def _run():
        from apps.dashboard.services import overview_for

        data = overview_for(user)
        # Évite de renvoyer des stats serveur WHM si présentes
        if isinstance(data, dict):
            data.pop("whm", None)
            data.pop("server", None)
        return data

    return run_service(_run)


@register_tool(
    name="get_my_package",
    description="Retourne le package hébergement assigné au compte (limites).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def get_my_package(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.packages.models import PackageAssignment

    assignment = (
        PackageAssignment.objects.filter(user=user).select_related("package").first()
    )
    if not assignment:
        return ok(package=None)
    pkg = assignment.package
    return ok(
        package={
            "id": pkg.pk,
            "name": pkg.name,
            "label": getattr(pkg, "label", "") or pkg.name,
            "disk_mb": getattr(pkg, "disk_mb", None),
            "bandwidth_mb": getattr(pkg, "bandwidth_mb", None),
            "max_domains": getattr(pkg, "max_domains", None),
            "max_databases": getattr(pkg, "max_databases", None),
            "max_email_accounts": getattr(pkg, "max_email_accounts", None),
            "max_ftp_accounts": getattr(pkg, "max_ftp_accounts", None),
            "max_cron_jobs": getattr(pkg, "max_cron_jobs", None),
        }
    )


@register_tool(
    name="get_security_status",
    description="Statut sécurité du compte (2FA activé ?, policy) — lecture seule, pas de changement MDP/2FA.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def get_security_status(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params

    def _run():
        from apps.security.services import my_security_status

        return my_security_status(user)

    return run_service(_run)
