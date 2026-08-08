"""Tools WordPress."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


@register_tool(
    name="list_wordpress_sites",
    description="Liste les sites WordPress du compte.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_wordpress_sites(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.wordpress.services import overview_for, sites_qs

    sites = [
        {
            "id": s.pk,
            "title": s.title,
            "domain_id": s.domain_id,
            "site_url": s.site_url,
            "status": s.status,
            "admin_url": s.admin_url,
        }
        for s in sites_qs(user)[:40]
    ]
    return ok(overview=overview_for(user), sites=sites)


@register_tool(
    name="install_wordpress",
    description=(
        "Installe WordPress sur un domaine du compte (confirmation requise). "
        "Accepte domain_id ou domain_name. Ne renvoie jamais le mot de passe admin en clair."
    ),
    parameters={
        "type": "object",
        "properties": {
            "domain_id": {"type": "integer"},
            "domain_name": {"type": "string"},
            "title": {"type": "string"},
            "admin_user": {"type": "string"},
            "admin_email": {"type": "string"},
            "admin_password": {"type": "string"},
            "locale": {"type": "string"},
        },
        "additionalProperties": False,
    },
    dangerous=True,
)
def install_wordpress(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.domains.services import domains_queryset_for
    from apps.wordpress.services import install_wordpress as svc

    domain_id = require_int(params, "domain_id")
    domain_name = require_str(params, "domain_name", max_len=253)
    if not domain_id and domain_name:
        d = domains_queryset_for(user).filter(name__iexact=domain_name.strip().lower()).first()
        if not d:
            return err(f"Domaine introuvable : {domain_name}", "not_found")
        domain_id = d.pk
    if not domain_id:
        return err("domain_id ou domain_name requis")

    def _run():
        site, _password = svc(
            owner=user,
            domain_id=domain_id,
            title=require_str(params, "title", default="Mon site", max_len=200),
            admin_user=require_str(params, "admin_user", default="admin", max_len=60) or "admin",
            admin_email=require_str(params, "admin_email", max_len=200),
            admin_password=str(params.get("admin_password") or ""),
            locale=require_str(params, "locale", default="fr_FR") or "fr_FR",
        )
        return {
            "id": site.pk,
            "title": site.title,
            "site_url": site.site_url,
            "admin_url": site.admin_url,
            "admin_user": site.admin_user,
            "status": site.status,
            "password_set": True,
            "note": "Mot de passe admin non affiché (sécurité). Utilisez celui fourni ou réinitialisez via WP.",
        }

    return run_service(_run)


@register_tool(
    name="delete_wordpress",
    description="Supprime une installation WordPress (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "site_id": {"type": "integer"},
            "remove_files": {"type": "boolean"},
            "remove_database": {"type": "boolean"},
        },
        "required": ["site_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_wordpress(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.wordpress.services import delete_wordpress as svc, sites_qs

    site = sites_qs(user).filter(pk=require_int(params, "site_id")).first()
    if not site:
        return err("Site WP introuvable", "not_found")
    title = site.title

    def _run():
        try:
            svc(
                site,
                remove_files=bool(params.get("remove_files", True)),
                remove_database=bool(params.get("remove_database", False)),
            )
        except TypeError:
            svc(site)
        return {"deleted": title}

    return run_service(_run)
