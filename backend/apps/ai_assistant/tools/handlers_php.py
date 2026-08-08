"""Tools sélecteurs PHP."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


def _selector_summary(sel) -> dict[str, Any]:
    return {
        "id": sel.pk,
        "relative_path": sel.relative_path,
        "domain_name": sel.domain_name or "",
        "handler": sel.handler,
        "php_version_id": sel.php_version_id,
        "php_version": sel.php_version.version if getattr(sel, "php_version", None) else None,
        "is_active": sel.is_active,
        "notes": sel.notes or "",
    }


@register_tool(
    name="list_php_versions",
    description="Liste les versions PHP disponibles sur le serveur.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_php_versions(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.php.services import ensure_default_versions, versions_qs

    ensure_default_versions()
    versions = [
        {
            "id": v.pk,
            "version": v.version,
            "is_default": v.is_default,
            "is_available": v.is_available,
        }
        for v in versions_qs()[:40]
    ]
    return ok(versions=versions)


@register_tool(
    name="list_php_selectors",
    description="Liste les sélecteurs PHP du compte.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_php_selectors(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.php.services import overview_for, selectors_qs

    selectors = [
        _selector_summary(s)
        for s in selectors_qs(user).select_related("php_version")[:80]
    ]
    return ok(overview=overview_for(user), selectors=selectors)


@register_tool(
    name="create_php_selector",
    description="Crée un sélecteur PHP pour un chemin (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "php_version_id": {"type": "integer"},
            "relative_path": {"type": "string"},
            "domain_name": {"type": "string"},
            "handler": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["php_version_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_php_selector(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.php.models import PhpSelector
    from apps.php.services import create_selector

    version_id = require_int(params, "php_version_id")
    if not version_id:
        return err("php_version_id requis")

    def _run():
        sel = create_selector(
            owner=user,
            php_version_id=version_id,
            relative_path=require_str(params, "relative_path", default="public_html") or "public_html",
            domain_name=require_str(params, "domain_name", max_len=253),
            handler=require_str(params, "handler", default=PhpSelector.Handler.FPM)
            or PhpSelector.Handler.FPM,
            notes=require_str(params, "notes", max_len=200),
        )
        return _selector_summary(sel)

    return run_service(_run)


@register_tool(
    name="update_php_selector",
    description="Modifie un sélecteur PHP (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "selector_id": {"type": "integer"},
            "php_version_id": {"type": "integer"},
            "domain_name": {"type": "string"},
            "handler": {"type": "string"},
            "notes": {"type": "string"},
            "is_active": {"type": "boolean"},
        },
        "required": ["selector_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def update_php_selector(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.php.services import selectors_qs, update_selector

    sel = selectors_qs(user).filter(pk=require_int(params, "selector_id")).first()
    if not sel:
        return err("Sélecteur PHP introuvable", "not_found")

    fields: dict[str, Any] = {}
    if "php_version_id" in params:
        fields["php_version_id"] = require_int(params, "php_version_id")
    if "domain_name" in params and params["domain_name"] is not None:
        fields["domain_name"] = require_str(params, "domain_name", max_len=253)
    if "handler" in params and params["handler"] is not None:
        fields["handler"] = require_str(params, "handler", max_len=32)
    if "notes" in params and params["notes"] is not None:
        fields["notes"] = require_str(params, "notes", max_len=200)
    if "is_active" in params:
        fields["is_active"] = bool(params["is_active"])

    def _run():
        return _selector_summary(update_selector(sel, **fields))

    return run_service(_run)


@register_tool(
    name="delete_php_selector",
    description="Supprime un sélecteur PHP (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"selector_id": {"type": "integer"}},
        "required": ["selector_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_php_selector(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.php.services import delete_selector, selectors_qs

    sel = selectors_qs(user).filter(pk=require_int(params, "selector_id")).first()
    if not sel:
        return err("Sélecteur PHP introuvable", "not_found")
    sid = sel.pk

    def _run():
        delete_selector(sel)
        return {"deleted": sid}

    return run_service(_run)
