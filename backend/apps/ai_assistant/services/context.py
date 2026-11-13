"""Contexte déploiement utilisateur (sans secrets) — scope compte strict."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.services.redaction import redact_text
from apps.ai_assistant.tools.helpers import (
    ai_domains_qs,
    ai_git_repos_qs,
    ai_node_apps_qs,
    ai_python_apps_qs,
)


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
        for a in ai_python_apps_qs(user)[:20]:
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
        for a in ai_node_apps_qs(user)[:20]:
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
        for r in ai_git_repos_qs(user)[:20]:
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
        for d in ai_domains_qs(user).order_by("name")[:30]:
            ctx["domains"].append({"id": d.pk, "name": d.name})
    except Exception:  # noqa: BLE001
        pass
    return ctx
