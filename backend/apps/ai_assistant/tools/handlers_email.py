"""Tools email (boîtes, forwarders, DKIM) — jamais de mots de passe en clair."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


def _mailbox_summary(box) -> dict[str, Any]:
    return {
        "id": box.pk,
        "address": f"{box.local_part}@{box.mail_domain.name}",
        "local_part": box.local_part,
        "domain": box.mail_domain.name,
        "domain_id": box.mail_domain_id,
        "quota_mb": box.quota_mb,
        "is_active": box.is_active,
        "is_suspended": box.is_suspended,
        "notes": box.notes or "",
    }


@register_tool(
    name="list_mailboxes",
    description="Liste les domaines mail et boîtes du compte (sans mots de passe).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_mailboxes(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.email.services import mail_domains_qs, mailboxes_qs

    domains = [
        {
            "id": d.pk,
            "name": d.name,
            "max_quota_mb": d.max_quota_mb,
            "dkim_enabled": bool(getattr(d, "dkim_enabled", False)),
            "dkim_selector": getattr(d, "dkim_selector", "") or "",
            "spf_record": (d.spf_record or "")[:200],
        }
        for d in mail_domains_qs(user)[:40]
    ]
    mailboxes = [_mailbox_summary(b) for b in mailboxes_qs(user).select_related("mail_domain")[:80]]
    return ok(domains=domains, mailboxes=mailboxes)


@register_tool(
    name="create_mailbox",
    description="Crée une boîte mail (confirmation requise). Le mot de passe n'est jamais renvoyé.",
    parameters={
        "type": "object",
        "properties": {
            "mail_domain_id": {"type": "integer"},
            "local_part": {"type": "string"},
            "password": {"type": "string"},
            "quota_mb": {"type": "integer"},
            "notes": {"type": "string"},
        },
        "required": ["mail_domain_id", "local_part", "password"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_mailbox(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.email.services import create_mailbox as svc, mail_domains_qs

    md = mail_domains_qs(user).filter(pk=require_int(params, "mail_domain_id")).first()
    if not md:
        return err("Domaine mail introuvable", "not_found")
    local_part = require_str(params, "local_part", max_len=64)
    password = str(params.get("password") or "")
    if not local_part or len(password) < 8:
        return err("local_part + password (≥8) requis")

    def _run():
        box = svc(
            mail_domain=md,
            local_part=local_part,
            password=password,
            quota_mb=require_int(params, "quota_mb"),
            notes=require_str(params, "notes", max_len=200),
        )
        data = _mailbox_summary(box)
        data["password_set"] = True
        return data

    return run_service(_run)


@register_tool(
    name="update_mailbox",
    description="Modifie une boîte mail (confirmation requise). Le mot de passe n'est jamais renvoyé.",
    parameters={
        "type": "object",
        "properties": {
            "mailbox_id": {"type": "integer"},
            "password": {"type": "string"},
            "quota_mb": {"type": "integer"},
            "is_active": {"type": "boolean"},
            "notes": {"type": "string"},
        },
        "required": ["mailbox_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def update_mailbox(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.email.services import mailboxes_qs, update_mailbox as svc

    box = mailboxes_qs(user).select_related("mail_domain").filter(pk=require_int(params, "mailbox_id")).first()
    if not box:
        return err("Boîte mail introuvable", "not_found")

    fields: dict[str, Any] = {}
    if "password" in params and params["password"] is not None:
        fields["password"] = str(params["password"])
    if "quota_mb" in params:
        fields["quota_mb"] = require_int(params, "quota_mb")
    if "is_active" in params:
        fields["is_active"] = bool(params["is_active"])
    if "notes" in params and params["notes"] is not None:
        fields["notes"] = require_str(params, "notes", max_len=200)

    def _run():
        updated = svc(box, **fields)
        data = _mailbox_summary(updated)
        if "password" in fields:
            data["password_set"] = True
        return data

    return run_service(_run)


@register_tool(
    name="suspend_mailbox",
    description="Suspend ou réactive une boîte mail (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "mailbox_id": {"type": "integer"},
            "suspended": {"type": "boolean"},
        },
        "required": ["mailbox_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def suspend_mailbox(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.email.services import mailboxes_qs, suspend_mailbox as svc

    box = mailboxes_qs(user).select_related("mail_domain").filter(pk=require_int(params, "mailbox_id")).first()
    if not box:
        return err("Boîte mail introuvable", "not_found")
    suspended = bool(params["suspended"]) if "suspended" in params else True

    def _run():
        return _mailbox_summary(svc(box, suspended=suspended))

    return run_service(_run)


@register_tool(
    name="delete_mailbox",
    description="Supprime une boîte mail (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"mailbox_id": {"type": "integer"}},
        "required": ["mailbox_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_mailbox(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.email.services import delete_mailbox as svc, mailboxes_qs

    box = mailboxes_qs(user).select_related("mail_domain").filter(pk=require_int(params, "mailbox_id")).first()
    if not box:
        return err("Boîte mail introuvable", "not_found")
    address = f"{box.local_part}@{box.mail_domain.name}"

    def _run():
        svc(box)
        return {"deleted": address}

    return run_service(_run)


@register_tool(
    name="create_mail_forwarder",
    description="Crée / met à jour un forwarder email (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "mail_domain_id": {"type": "integer"},
            "local_part": {"type": "string"},
            "destinations": {"type": "array", "items": {"type": "string"}},
            "keep_copy": {"type": "boolean"},
        },
        "required": ["mail_domain_id", "local_part", "destinations"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_mail_forwarder(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.email.services import create_forwarder, mail_domains_qs

    md = mail_domains_qs(user).filter(pk=require_int(params, "mail_domain_id")).first()
    if not md:
        return err("Domaine mail introuvable", "not_found")
    local_part = require_str(params, "local_part", max_len=64)
    destinations = params.get("destinations")
    if not local_part or not isinstance(destinations, list) or not destinations:
        return err("local_part + destinations requis")

    def _run():
        fwd = create_forwarder(
            mail_domain=md,
            local_part=local_part,
            destinations=[str(d) for d in destinations],
            keep_copy=bool(params.get("keep_copy", False)),
        )
        return {
            "id": fwd.pk,
            "local_part": fwd.local_part,
            "domain": md.name,
            "destinations": fwd.destinations,
            "keep_copy": fwd.keep_copy,
        }

    return run_service(_run)


@register_tool(
    name="enable_dkim",
    description="Active / régénère DKIM pour un domaine mail (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "mail_domain_id": {"type": "integer"},
            "selector": {"type": "string"},
        },
        "required": ["mail_domain_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def enable_dkim(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.email.services import enable_dkim as svc, mail_domains_qs

    md = mail_domains_qs(user).filter(pk=require_int(params, "mail_domain_id")).first()
    if not md:
        return err("Domaine mail introuvable", "not_found")
    selector = require_str(params, "selector", default="default", max_len=32) or "default"

    def _run():
        updated = svc(md, selector=selector)
        # Ne jamais renvoyer les clés privées DKIM
        return {
            "id": updated.pk,
            "name": updated.name,
            "selector": getattr(updated, "dkim_selector", selector) or selector,
            "dkim_enabled": True,
        }

    return run_service(_run)


@register_tool(
    name="sync_mail_dns",
    description="Synchronise les enregistrements DNS mail (SPF/MX/DKIM) (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"mail_domain_id": {"type": "integer"}},
        "required": ["mail_domain_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def sync_mail_dns(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.email.services import mail_domains_qs, sync_mail_dns as svc

    md = mail_domains_qs(user).filter(pk=require_int(params, "mail_domain_id")).first()
    if not md:
        return err("Domaine mail introuvable", "not_found")

    return run_service(lambda: svc(md))
