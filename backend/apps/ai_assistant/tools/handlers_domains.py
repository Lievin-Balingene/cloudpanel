"""Tools domaines + SSL."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


def _owned_domain(user: User, domain_id: int | None = None, name: str = ""):
    from apps.domains.services import domains_queryset_for

    qs = domains_queryset_for(user)
    if domain_id:
        return qs.filter(pk=domain_id).first()
    if name:
        return qs.filter(name__iexact=name.strip().lower()).first()
    return None


@register_tool(
    name="list_domains",
    description="Liste les domaines du compte (nom, type, SSL, docroot).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_domains(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.domains.services import domains_queryset_for
    from apps.domains.ssl_services import has_active_cert_files

    items = []
    for d in domains_queryset_for(user)[:80]:
        items.append(
            {
                "id": d.pk,
                "name": d.name,
                "type": d.domain_type,
                "document_root": getattr(d, "document_root", "") or "",
                "ssl": has_active_cert_files(d.name),
                "is_active": getattr(d, "is_active", True),
            }
        )
    return ok(domains=items)


@register_tool(
    name="get_ssl_status",
    description="Statut SSL d'un domaine (id ou name).",
    parameters={
        "type": "object",
        "properties": {
            "domain_id": {"type": "integer"},
            "domain_name": {"type": "string"},
        },
        "additionalProperties": False,
    },
)
def get_ssl_status(user: User, params: dict[str, Any]) -> dict[str, Any]:
    domain = _owned_domain(
        user, require_int(params, "domain_id"), require_str(params, "domain_name")
    )
    if not domain:
        return err("Domaine introuvable", "not_found")
    from apps.domains.ssl_services import has_active_cert_files

    return ok(domain_id=domain.pk, name=domain.name, ssl_active=has_active_cert_files(domain.name))


@register_tool(
    name="create_domain",
    description="Crée un domaine ou sous-domaine (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "domain_type": {
                "type": "string",
                "enum": ["primary", "addon", "subdomain", "parked", "alias"],
            },
            "parent_id": {"type": "integer"},
            "create_dns_zone": {"type": "boolean"},
            "document_root": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_domain(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.domains.models import Domain
    from apps.domains.services import create_domain as svc_create

    name = require_str(params, "name", max_len=253)
    if not name:
        return err("name requis", "invalid_params")
    dtype = require_str(params, "domain_type", default=Domain.DomainType.ADDON) or Domain.DomainType.ADDON
    parent = None
    parent_id = require_int(params, "parent_id")
    if parent_id:
        parent = _owned_domain(user, parent_id)
        if not parent:
            return err("parent_id introuvable", "not_found")

    def _run():
        d = svc_create(
            name=name,
            owner=user,
            domain_type=dtype,
            parent=parent,
            create_dns_zone=bool(params.get("create_dns_zone", True)),
            document_root=require_str(params, "document_root", max_len=500),
        )
        return {"id": d.pk, "name": d.name, "type": d.domain_type}

    return run_service(_run)


@register_tool(
    name="delete_domain",
    description="Supprime un domaine du compte (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "domain_id": {"type": "integer"},
            "remove_dns_zone": {"type": "boolean"},
        },
        "required": ["domain_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_domain(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.domains.services import delete_domain as svc_delete

    domain = _owned_domain(user, require_int(params, "domain_id"))
    if not domain:
        return err("Domaine introuvable", "not_found")
    name = domain.name

    def _run():
        svc_delete(domain, remove_dns_zone=bool(params.get("remove_dns_zone", False)))
        return {"deleted": name}

    return run_service(_run)


@register_tool(
    name="create_redirect",
    description="Crée une redirection HTTP pour un domaine (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "domain_id": {"type": "integer"},
            "source_path": {"type": "string"},
            "target_url": {"type": "string"},
            "redirect_type": {"type": "integer"},
        },
        "required": ["domain_id", "target_url"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_redirect(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.domains.services import create_redirect as svc_redirect

    domain = _owned_domain(user, require_int(params, "domain_id"))
    if not domain:
        return err("Domaine introuvable", "not_found")
    target = require_str(params, "target_url", max_len=500)
    if not target:
        return err("target_url requis", "invalid_params")

    def _run():
        r = svc_redirect(
            domain=domain,
            source_path=require_str(params, "source_path", default="/", max_len=200) or "/",
            destination_url=target,
            redirect_type=str(params.get("redirect_type") or "301"),
        )
        return {"id": getattr(r, "pk", None), "target": target}

    return run_service(_run)


@register_tool(
    name="issue_ssl_certificate",
    description="Émet un certificat Let's Encrypt pour un domaine (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "domain_id": {"type": "integer"},
            "email": {"type": "string"},
        },
        "required": ["domain_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def issue_ssl_certificate(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.domains.ssl_services import issue_letsencrypt

    domain = _owned_domain(user, require_int(params, "domain_id"))
    if not domain:
        return err("Domaine introuvable", "not_found")
    email = require_str(params, "email", max_len=200) or None

    def _run():
        cert = issue_letsencrypt(domain, email=email)
        return {
            "domain": domain.name,
            "status": getattr(cert, "status", "issued"),
            "id": getattr(cert, "pk", None),
        }

    return run_service(_run)
