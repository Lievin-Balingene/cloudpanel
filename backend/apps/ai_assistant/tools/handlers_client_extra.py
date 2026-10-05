"""Tools panneau client manquants + ciblage compte (WHM → client)."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import (
    err,
    ok,
    require_int,
    require_str,
    run_service,
)


def _ACCOUNT_PROPS() -> dict[str, Any]:
    return {
        "username": {
            "type": "string",
            "description": "Compte client cible (WHM/revendeur). Ignoré pour un client.",
        },
        "account": {
            "type": "string",
            "description": "Alias de username.",
        },
    }


@register_tool(
    name="list_ai_capabilities",
    description=(
        "Liste toutes les capacités / tools IA disponibles (lecture + mutations confirmables). "
        "Utilise pour répondre « qu'est-ce que tu peux faire ? »."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_ai_capabilities(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.ai_assistant.tools import ensure_tools_loaded, list_tool_specs

    ensure_tools_loaded()
    specs = list_tool_specs(include_dangerous=True)
    from apps.ai_assistant.tools import get_tool

    rows = []
    for s in sorted(specs, key=lambda x: x.name):
        tool = get_tool(s.name)
        rows.append(
            {
                "name": s.name,
                "description": s.description,
                "needs_confirmation": bool(tool.dangerous) if tool else False,
            }
        )
    return ok(
        count=len(rows),
        role=user.role,
        note=(
            "WHM/revendeur : passez username=compte_client ou utilisez set_working_account "
            "pour agir dans un compte client."
            if user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}
            else "Toutes les actions portent sur votre compte."
        ),
        tools=rows,
    )


@register_tool(
    name="list_client_accounts",
    description="Liste les comptes clients accessibles (WHM = tous, revendeur = ses clients).",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Filtre username/domaine (optionnel)"},
            "limit": {"type": "integer"},
        },
        "additionalProperties": False,
    },
)
def list_client_accounts(user: User, params: dict[str, Any]) -> dict[str, Any]:
    if user.role == User.Role.CLIENT:
        return err("Réservé WHM / revendeur.", "forbidden")
    q = require_str(params, "query", max_len=80).lower()
    limit = max(1, min(int(require_int(params, "limit") or 50), 200))
    qs = User.objects.filter(role=User.Role.CLIENT)
    if user.role == User.Role.RESELLER:
        qs = qs.filter(parent=user)
    if q:
        from django.db.models import Q

        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))
    from apps.domains.models import Domain

    rows = []
    for u in qs.order_by("username")[:limit]:
        primary = (
            Domain.objects.filter(owner=u, domain_type=Domain.DomainType.PRIMARY)
            .values_list("name", flat=True)
            .first()
            or Domain.objects.filter(owner=u).order_by("id").values_list("name", flat=True).first()
            or ""
        )
        rows.append(
            {
                "id": u.pk,
                "username": u.username,
                "email": u.email,
                "domain": primary,
                "suspended": bool(u.is_suspended),
            }
        )
    return ok(count=len(rows), accounts=rows)


@register_tool(
    name="set_working_account",
    description=(
        "Définit le compte client de travail pour les prochains tools (WHM/revendeur). "
        "Confirmation requise."
    ),
    parameters={
        "type": "object",
        "properties": {
            "username": {"type": "string"},
            "account": {"type": "string"},
        },
        "required": ["username"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def set_working_account(user: User, params: dict[str, Any]) -> dict[str, Any]:
    """`user` = compte cible déjà résolu par l'agent (via username=)."""
    del params
    return ok(
        working_account=user.username,
        account_id=user.pk,
        message=f"Compte de travail : {user.username}. Les prochains tools cibleront ce compte.",
        _set_working_account=user.username,
    )


@register_tool(
    name="clear_working_account",
    description="Annule le compte de travail (revient au compte de la session).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    dangerous=True,
)
def clear_working_account(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    return ok(
        working_account=None,
        message="Compte de travail effacé.",
        _clear_working_account=True,
    )


@register_tool(
    name="get_disk_usage",
    description="Utilisation disque du compte (home, quotas).",
    parameters={
        "type": "object",
        "properties": {**_ACCOUNT_PROPS()},
        "additionalProperties": False,
    },
)
def get_disk_usage(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user

    def _run():
        from apps.dashboard.services import account_disk_usage

        return account_disk_usage(owner)

    return run_service(_run)


@register_tool(
    name="get_visitor_metrics",
    description="Métriques visiteurs / erreurs (logs Nginx) pour les domaines du compte.",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "hours": {"type": "integer", "description": "Fenêtre en heures (défaut 24)"},
        },
        "additionalProperties": False,
    },
)
def get_visitor_metrics(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user
    hours = int(require_int(params, "hours") or 24)

    def _run():
        from apps.dashboard.services import visitors_for

        return visitors_for(owner, hours=hours)

    return run_service(_run)


@register_tool(
    name="list_ssh_keys",
    description="Liste les clés SSH autorisées du compte (~/.ssh/authorized_keys).",
    parameters={
        "type": "object",
        "properties": {**_ACCOUNT_PROPS()},
        "additionalProperties": False,
    },
)
def list_ssh_keys_tool(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user

    def _run():
        from apps.security.services import list_ssh_keys

        return {"keys": list_ssh_keys(owner)}

    return run_service(_run)


@register_tool(
    name="add_ssh_key",
    description="Ajoute une clé publique SSH au compte (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "name": {"type": "string"},
            "public_key": {"type": "string"},
        },
        "required": ["public_key"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def add_ssh_key_tool(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user
    name = require_str(params, "name", max_len=255)
    public_key = require_str(params, "public_key", max_len=8000)
    if not public_key:
        return err("public_key requis", "invalid_params")

    def _run():
        from apps.security.services import add_ssh_key

        return add_ssh_key(owner, name=name, public_key=public_key)

    return run_service(_run)


@register_tool(
    name="delete_ssh_key",
    description="Supprime une clé SSH par index ou fingerprint (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "key_id": {"type": "integer", "description": "Index de la clé"},
            "fingerprint": {"type": "string"},
        },
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_ssh_key_tool(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user
    key_id = require_int(params, "key_id")
    fingerprint = require_str(params, "fingerprint", max_len=128)
    target = fingerprint or key_id
    if target is None or target == "":
        return err("key_id ou fingerprint requis", "invalid_params")

    def _run():
        from apps.security.services import delete_ssh_key

        delete_ssh_key(owner, target)
        return {"deleted": True, "target": str(target)}

    return run_service(_run)


@register_tool(
    name="list_blocked_ips",
    description="Liste les IP bloquées du compte (etc/ip_blocker.txt).",
    parameters={
        "type": "object",
        "properties": {**_ACCOUNT_PROPS()},
        "additionalProperties": False,
    },
)
def list_blocked_ips(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user

    def _run():
        from apps.files.services import read_file

        try:
            data = read_file(owner, "etc/ip_blocker.txt")
            content = data.get("content") if isinstance(data, dict) else str(data)
        except Exception:  # noqa: BLE001
            content = ""
        lines = [ln.strip() for ln in str(content or "").splitlines() if ln.strip()]
        return {"ips": lines, "count": len(lines)}

    return run_service(_run)


@register_tool(
    name="block_client_ip",
    description="Ajoute une IP/CIDR à la liste de blocage du compte (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "ip": {"type": "string"},
        },
        "required": ["ip"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def block_client_ip(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user
    ip = require_str(params, "ip", max_len=64)
    if not ip or " " in ip:
        return err("IP/CIDR invalide", "invalid_params")

    def _run():
        from apps.files.services import mkdir, read_file, write_file

        try:
            mkdir(owner, "", "etc")
        except Exception:  # noqa: BLE001
            pass
        try:
            data = read_file(owner, "etc/ip_blocker.txt")
            content = data.get("content") if isinstance(data, dict) else str(data)
        except Exception:  # noqa: BLE001
            content = ""
        lines = [ln.strip() for ln in str(content or "").splitlines() if ln.strip()]
        if ip not in lines:
            lines.append(ip)
        write_file(owner, "etc/ip_blocker.txt", "\n".join(lines) + ("\n" if lines else ""))
        return {"ips": lines, "added": ip}

    return run_service(_run)


@register_tool(
    name="unblock_client_ip",
    description="Retire une IP de la liste de blocage du compte (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "ip": {"type": "string"},
        },
        "required": ["ip"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def unblock_client_ip(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user
    ip = require_str(params, "ip", max_len=64)

    def _run():
        from apps.files.services import read_file, write_file

        try:
            data = read_file(owner, "etc/ip_blocker.txt")
            content = data.get("content") if isinstance(data, dict) else str(data)
        except Exception:  # noqa: BLE001
            content = ""
        lines = [ln.strip() for ln in str(content or "").splitlines() if ln.strip() and ln.strip() != ip]
        write_file(owner, "etc/ip_blocker.txt", "\n".join(lines) + ("\n" if lines else ""))
        return {"ips": lines, "removed": ip}

    return run_service(_run)


@register_tool(
    name="get_directory_privacy",
    description="Statut protection .htpasswd d'un dossier du compte.",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "path": {"type": "string", "description": "Chemin relatif au home"},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)
def get_directory_privacy(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user
    path = require_str(params, "path", max_len=500)

    def _run():
        from apps.files.services import directory_privacy_status

        return directory_privacy_status(owner, path)

    return run_service(_run)


@register_tool(
    name="enable_directory_privacy",
    description="Active la protection par mot de passe d'un dossier (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "path": {"type": "string"},
            "ht_username": {
                "type": "string",
                "description": "Login HTTP Basic (.htpasswd), pas le compte panel",
            },
            "password": {"type": "string"},
        },
        "required": ["path", "ht_username", "password"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def enable_directory_privacy_tool(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user
    path = require_str(params, "path", max_len=500)
    htuser = require_str(params, "ht_username", max_len=64)
    password = require_str(params, "password", max_len=128)
    if not path or not htuser or not password:
        return err("path, ht_username et password requis", "invalid_params")

    def _run():
        from apps.files.services import enable_directory_privacy

        return enable_directory_privacy(owner, path, username=htuser, password=password)

    return run_service(_run)


@register_tool(
    name="disable_directory_privacy",
    description="Désactive la protection d'un dossier (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "path": {"type": "string"},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def disable_directory_privacy_tool(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user
    path = require_str(params, "path", max_len=500)

    def _run():
        from apps.files.services import disable_directory_privacy

        return disable_directory_privacy(owner, path)

    return run_service(_run)


@register_tool(
    name="list_redirects",
    description="Liste les redirections HTTP d'un domaine du compte.",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "domain_id": {"type": "integer"},
            "domain_name": {"type": "string"},
        },
        "additionalProperties": False,
    },
)
def list_redirects(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user

    def _run():
        from apps.domains.models import DomainRedirect
        from apps.domains.services import domains_queryset_for

        qs = domains_queryset_for(owner)
        domain_id = require_int(params, "domain_id")
        domain_name = require_str(params, "domain_name", max_len=253)
        if domain_id:
            qs = qs.filter(pk=domain_id)
        elif domain_name:
            qs = qs.filter(name__iexact=domain_name)
        domain_ids = list(qs.values_list("id", flat=True)[:50])
        rows = []
        for r in DomainRedirect.objects.filter(domain_id__in=domain_ids).select_related("domain")[:100]:
            rows.append(
                {
                    "id": r.pk,
                    "domain": r.domain.name,
                    "domain_id": r.domain_id,
                    "source_path": r.source_path,
                    "destination_url": r.destination_url,
                    "redirect_type": r.redirect_type,
                    "is_active": r.is_active,
                }
            )
        return {"redirects": rows, "count": len(rows)}

    return run_service(_run)


@register_tool(
    name="delete_redirect",
    description="Supprime une redirection HTTP (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "redirect_id": {"type": "integer"},
            "domain_id": {"type": "integer"},
        },
        "required": ["redirect_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_redirect(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user
    redirect_id = require_int(params, "redirect_id")
    if not redirect_id:
        return err("redirect_id requis", "invalid_params")

    def _run():
        from apps.domains.models import DomainRedirect
        from apps.domains.services import domains_queryset_for

        allowed = domains_queryset_for(owner)
        r = DomainRedirect.objects.filter(pk=redirect_id, domain__in=allowed).first()
        if not r:
            raise Exception("Redirection introuvable")
        info = {"id": r.pk, "domain": r.domain.name, "source_path": r.source_path}
        r.delete()
        return info

    return run_service(_run)


@register_tool(
    name="list_mail_forwarders",
    description="Liste les forwarders e-mail du compte.",
    parameters={
        "type": "object",
        "properties": {**_ACCOUNT_PROPS()},
        "additionalProperties": False,
    },
)
def list_mail_forwarders(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user

    def _run():
        from apps.email.models import MailForwarder
        from apps.email.services import mail_domains_qs

        domains = mail_domains_qs(owner)
        rows = []
        for f in MailForwarder.objects.filter(mail_domain__in=domains).select_related("mail_domain")[:100]:
            rows.append(
                {
                    "id": f.pk,
                    "address": f"{f.local_part}@{f.mail_domain.name}",
                    "destinations": f.destinations,
                    "is_active": f.is_active,
                }
            )
        return {"forwarders": rows, "count": len(rows)}

    return run_service(_run)


@register_tool(
    name="delete_mail_forwarder",
    description="Supprime un forwarder e-mail (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            **_ACCOUNT_PROPS(),
            "forwarder_id": {"type": "integer"},
        },
        "required": ["forwarder_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_mail_forwarder(user: User, params: dict[str, Any]) -> dict[str, Any]:
    owner = user
    forwarder_id = require_int(params, "forwarder_id")
    if not forwarder_id:
        return err("forwarder_id requis", "invalid_params")

    def _run():
        from apps.email.models import MailForwarder
        from apps.email.services import mail_domains_qs

        domains = mail_domains_qs(owner)
        f = MailForwarder.objects.filter(pk=forwarder_id, mail_domain__in=domains).first()
        if not f:
            raise Exception("Forwarder introuvable")
        info = {"id": f.pk, "address": f"{f.local_part}@{f.mail_domain.name}"}
        f.delete()
        from apps.email.services import write_mail_maps

        write_mail_maps()
        return info

    return run_service(_run)

