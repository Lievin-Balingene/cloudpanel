"""Contexte déploiement utilisateur (sans secrets)."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.services.redaction import redact_text


def build_user_context(user: User) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "username": user.username,
        "role": getattr(user, "role", ""),
        "python_apps": [],
        "node_apps": [],
        "git_repos": [],
        "domains": [],
        "missing_for_deploy": [
            "repository",
            "branch",
            "runtime",
            "runtime_version",
            "domain",
            "database",
            "env_var_names",
            "install_command",
            "start_command",
        ],
    }
    try:
        from apps.python_apps.services import apps_qs

        for a in apps_qs(user)[:20]:
            ctx["python_apps"].append(
                {
                    "id": a.pk,
                    "name": a.name,
                    "status": a.status,
                    "port": a.port,
                    "python_version": getattr(a, "python_version", ""),
                    "domain": getattr(a, "domain_name", "") or "",
                    "last_error": redact_text(getattr(a, "last_error", "") or "", max_len=200),
                }
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.node_apps.services import apps_qs

        for a in apps_qs(user)[:20]:
            ctx["node_apps"].append(
                {
                    "id": a.pk,
                    "name": a.name,
                    "status": a.status,
                    "port": a.port,
                    "start_script": getattr(a, "start_script", ""),
                    "last_error": redact_text(getattr(a, "last_error", "") or "", max_len=200),
                }
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.git_deploy.services import repos_qs

        for r in repos_qs(user)[:20]:
            ctx["git_repos"].append(
                {
                    "id": r.pk,
                    "name": r.name,
                    "remote_url": r.remote_url,
                    "branch": r.branch,
                    "status": r.status,
                    "last_error": redact_text(r.last_error or "", max_len=200),
                    "last_commit": r.last_commit,
                }
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        from apps.domains.models import Domain

        qs = Domain.objects.all()
        if user.role == User.Role.CLIENT:
            qs = qs.filter(owner=user)
        elif user.role == User.Role.RESELLER:
            qs = qs.filter(owner__parent=user) | qs.filter(owner=user)
        for d in qs.order_by("name")[:30]:
            ctx["domains"].append({"id": d.pk, "name": d.name})
    except Exception:  # noqa: BLE001
        pass
    return ctx
