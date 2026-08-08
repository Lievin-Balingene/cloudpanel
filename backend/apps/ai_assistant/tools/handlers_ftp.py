"""Tools comptes FTP."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


def _ftp_summary(account) -> dict[str, Any]:
    return {
        "id": account.pk,
        "username": account.username,
        "relative_directory": account.relative_directory,
        "quota_mb": account.quota_mb,
        "bandwidth_kbs": account.bandwidth_kbs,
        "can_write": account.can_write,
        "is_active": account.is_active,
        "is_suspended": account.is_suspended,
        "notes": account.notes or "",
    }


@register_tool(
    name="list_ftp_accounts",
    description="Liste les comptes FTP du compte (sans mots de passe).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_ftp_accounts(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.ftp.services import accounts_queryset_for

    accounts = [_ftp_summary(a) for a in accounts_queryset_for(user)[:80]]
    return ok(accounts=accounts, count=len(accounts))


@register_tool(
    name="create_ftp_account",
    description="Crée un compte FTP (confirmation requise). Le mot de passe n'est jamais renvoyé.",
    parameters={
        "type": "object",
        "properties": {
            "username": {"type": "string"},
            "password": {"type": "string"},
            "relative_directory": {"type": "string"},
            "quota_mb": {"type": "integer"},
            "bandwidth_kbs": {"type": "integer"},
            "can_write": {"type": "boolean"},
            "notes": {"type": "string"},
        },
        "required": ["username", "password"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_ftp_account(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.ftp.services import create_ftp_account as svc

    username = require_str(params, "username", max_len=64)
    password = str(params.get("password") or "")
    if not username or len(password) < 8:
        return err("username + password (≥8) requis")

    def _run():
        account = svc(
            owner=user,
            username=username,
            password=password,
            relative_directory=require_str(params, "relative_directory", default="public_html")
            or "public_html",
            quota_mb=require_int(params, "quota_mb") or 0,
            bandwidth_kbs=require_int(params, "bandwidth_kbs") or 0,
            can_write=bool(params["can_write"]) if "can_write" in params else True,
            notes=require_str(params, "notes", max_len=200),
        )
        data = _ftp_summary(account)
        data["password_set"] = True
        return data

    return run_service(_run)


@register_tool(
    name="update_ftp_account",
    description="Modifie un compte FTP (confirmation requise). Le mot de passe n'est jamais renvoyé.",
    parameters={
        "type": "object",
        "properties": {
            "account_id": {"type": "integer"},
            "password": {"type": "string"},
            "relative_directory": {"type": "string"},
            "quota_mb": {"type": "integer"},
            "bandwidth_kbs": {"type": "integer"},
            "can_write": {"type": "boolean"},
            "notes": {"type": "string"},
            "is_active": {"type": "boolean"},
        },
        "required": ["account_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def update_ftp_account(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.ftp.services import accounts_queryset_for, update_ftp_account as svc

    account = accounts_queryset_for(user).filter(pk=require_int(params, "account_id")).first()
    if not account:
        return err("Compte FTP introuvable", "not_found")

    fields: dict[str, Any] = {}
    if "password" in params and params["password"] is not None:
        fields["password"] = str(params["password"])
    if "relative_directory" in params and params["relative_directory"] is not None:
        fields["relative_directory"] = require_str(params, "relative_directory", max_len=500)
    if "quota_mb" in params:
        fields["quota_mb"] = require_int(params, "quota_mb")
    if "bandwidth_kbs" in params:
        fields["bandwidth_kbs"] = require_int(params, "bandwidth_kbs")
    if "can_write" in params:
        fields["can_write"] = bool(params["can_write"])
    if "notes" in params and params["notes"] is not None:
        fields["notes"] = require_str(params, "notes", max_len=200)
    if "is_active" in params:
        fields["is_active"] = bool(params["is_active"])

    def _run():
        updated = svc(account, **fields)
        data = _ftp_summary(updated)
        if "password" in fields:
            data["password_set"] = True
        return data

    return run_service(_run)


@register_tool(
    name="suspend_ftp_account",
    description="Suspend ou réactive un compte FTP (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "account_id": {"type": "integer"},
            "suspended": {"type": "boolean"},
        },
        "required": ["account_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def suspend_ftp_account(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.ftp.services import accounts_queryset_for, suspend_ftp_account as svc

    account = accounts_queryset_for(user).filter(pk=require_int(params, "account_id")).first()
    if not account:
        return err("Compte FTP introuvable", "not_found")
    suspended = bool(params["suspended"]) if "suspended" in params else True

    def _run():
        return _ftp_summary(svc(account, suspended=suspended))

    return run_service(_run)


@register_tool(
    name="delete_ftp_account",
    description="Supprime un compte FTP (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "account_id": {"type": "integer"},
            "remove_directory": {"type": "boolean"},
        },
        "required": ["account_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_ftp_account(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.ftp.services import accounts_queryset_for, delete_ftp_account as svc

    account = accounts_queryset_for(user).filter(pk=require_int(params, "account_id")).first()
    if not account:
        return err("Compte FTP introuvable", "not_found")
    username = account.username

    def _run():
        svc(account, remove_directory=bool(params.get("remove_directory", False)))
        return {"deleted": username}

    return run_service(_run)
