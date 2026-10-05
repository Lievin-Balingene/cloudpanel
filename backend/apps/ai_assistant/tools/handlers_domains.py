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


def _resolve_parent_domain(user: User, name: str, *, parent_id: int | None = None, parent_name: str = ""):
    """Trouve le domaine parent pour un hostname (ex: nature.7une.info → 7une.info)."""
    from apps.domains.models import Domain
    from apps.domains.services import domains_queryset_for

    if parent_id:
        found = _owned_domain(user, parent_id)
        if not found:
            raise ValueError("parent_id introuvable")
        return found
    if parent_name:
        found = _owned_domain(user, name=parent_name)
        if not found:
            raise ValueError(f"Domaine parent introuvable : {parent_name}")
        return found

    parts = name.split(".")
    # nature.7une.info → essaie 7une.info, puis une.info (suffixes)
    if len(parts) < 3:
        return None
    qs = domains_queryset_for(user).exclude(
        domain_type__in={Domain.DomainType.ALIAS, Domain.DomainType.PARKED}
    )
    for i in range(1, len(parts) - 1):
        candidate = ".".join(parts[i:])
        found = qs.filter(name__iexact=candidate).first()
        if found and name.endswith("." + found.name):
            return found
    return None


@register_tool(
    name="create_domain",
    description=(
        "Crée un domaine ou sous-domaine (confirmation requise). "
        "Pour un sous-domaine (ex: nature.7une.info), parent_id/parent_name sont optionnels : "
        "le parent est auto-détecté s'il existe déjà sur le compte."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "domain_type": {
                "type": "string",
                "enum": ["primary", "addon", "subdomain", "parked", "alias"],
            },
            "parent_id": {"type": "integer"},
            "parent_name": {
                "type": "string",
                "description": "Nom du domaine parent (ex: 7une.info). Alternative à parent_id.",
            },
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
    name = name.strip().lower().rstrip(".")
    dtype = (require_str(params, "domain_type", default="") or "").strip().lower()

    try:
        parent = _resolve_parent_domain(
            user,
            name,
            parent_id=require_int(params, "parent_id"),
            parent_name=require_str(params, "parent_name", max_len=253),
        )
    except ValueError as exc:
        return err(str(exc), "not_found")

    # Auto-type : hostname sous un domaine du compte → subdomain, sinon addon
    if not dtype:
        dtype = Domain.DomainType.SUBDOMAIN if parent else Domain.DomainType.ADDON
    elif dtype == Domain.DomainType.SUBDOMAIN and parent is None:
        # L'IA a souvent mis domain_type=subdomain sans parent_id — retente
        parent = _resolve_parent_domain(user, name)
        if parent is None:
            return err(
                "Sous-domaine : aucun domaine parent trouvé sur le compte "
                f"(ex: pour {name}, créez d'abord le domaine parent).",
                "invalid_params",
            )
    elif (
        dtype in {Domain.DomainType.ADDON, Domain.DomainType.PRIMARY}
        and parent is not None
        and name.endswith("." + parent.name)
        and name != parent.name
    ):
        # nature.7une.info passé en addon alors que 7une.info existe → subdomain
        dtype = Domain.DomainType.SUBDOMAIN

    if dtype == Domain.DomainType.SUBDOMAIN and parent is None:
        return err(
            "Sous-domaine : parent_id / parent_name requis (ou domaine parent absent).",
            "invalid_params",
        )

    def _run():
        d = svc_create(
            name=name,
            owner=user,
            domain_type=dtype,
            parent=parent,
            create_dns_zone=bool(params.get("create_dns_zone", True)),
            document_root=require_str(params, "document_root", max_len=500),
        )
        return {
            "id": d.pk,
            "name": d.name,
            "type": d.domain_type,
            "parent_id": parent.pk if parent else None,
            "parent_name": parent.name if parent else None,
        }

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
    description=(
        "Émet un certificat Let's Encrypt pour un domaine (confirmation requise). "
        "Accepte domain_id ou domain_name."
    ),
    parameters={
        "type": "object",
        "properties": {
            "domain_id": {"type": "integer"},
            "domain_name": {"type": "string"},
            "email": {"type": "string"},
        },
        "additionalProperties": False,
    },
    dangerous=True,
)
def issue_ssl_certificate(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.domains.ssl_services import issue_letsencrypt

    domain = _owned_domain(
        user,
        require_int(params, "domain_id"),
        require_str(params, "domain_name", max_len=253),
    )
    if not domain:
        return err("Domaine introuvable (domain_id ou domain_name)", "not_found")
    email = require_str(params, "email", max_len=200) or None

    def _run():
        cert = issue_letsencrypt(domain, email=email)
        return {
            "domain": domain.name,
            "status": getattr(cert, "status", "issued"),
            "id": getattr(cert, "pk", None),
        }

    return run_service(_run)
