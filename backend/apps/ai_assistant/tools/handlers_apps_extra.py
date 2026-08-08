"""Tools apps Python / Node (création / update / delete)."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, require_int, require_str, run_service


def _python_summary(app) -> dict[str, Any]:
    return {
        "id": app.pk,
        "name": app.name,
        "label": app.label or "",
        "python_version": app.python_version,
        "mode": app.mode,
        "framework": app.framework,
        "relative_root": app.relative_root,
        "entrypoint": app.entrypoint,
        "domain_name": app.domain_name or "",
        "port": app.port,
        "status": app.status,
        "is_active": app.is_active,
    }


def _node_summary(app) -> dict[str, Any]:
    return {
        "id": app.pk,
        "name": app.name,
        "label": app.label or "",
        "node_version": app.node_version,
        "framework": app.framework,
        "relative_root": app.relative_root,
        "start_script": app.start_script,
        "entrypoint": app.entrypoint,
        "domain_name": app.domain_name or "",
        "port": app.port,
        "status": app.status,
        "is_active": app.is_active,
    }


@register_tool(
    name="create_python_app",
    description="Crée une application Python (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "label": {"type": "string"},
            "python_version": {"type": "string"},
            "mode": {"type": "string"},
            "framework": {"type": "string"},
            "relative_root": {"type": "string"},
            "entrypoint": {"type": "string"},
            "domain_name": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_python_app(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.python_apps.models import PythonApp
    from apps.python_apps.services import create_python_app as svc

    name = require_str(params, "name", max_len=64)
    if not name:
        return err("name requis")

    def _run():
        app = svc(
            owner=user,
            name=name,
            label=require_str(params, "label", max_len=120),
            python_version=require_str(params, "python_version", default="3.12") or "3.12",
            mode=require_str(params, "mode", default=PythonApp.Mode.WSGI) or PythonApp.Mode.WSGI,
            framework=require_str(params, "framework", default=PythonApp.Framework.GENERIC)
            or PythonApp.Framework.GENERIC,
            relative_root=require_str(params, "relative_root", max_len=500),
            entrypoint=require_str(params, "entrypoint", max_len=200),
            domain_name=require_str(params, "domain_name", max_len=253),
            notes=require_str(params, "notes", max_len=200),
        )
        return _python_summary(app)

    return run_service(_run)


@register_tool(
    name="update_python_app",
    description="Met à jour une application Python (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "app_id": {"type": "integer"},
            "label": {"type": "string"},
            "entrypoint": {"type": "string"},
            "domain_name": {"type": "string"},
            "notes": {"type": "string"},
            "is_active": {"type": "boolean"},
        },
        "required": ["app_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def update_python_app(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.python_apps.services import apps_qs, update_python_app as svc

    app = apps_qs(user).filter(pk=require_int(params, "app_id")).first()
    if not app:
        return err("Application Python introuvable", "not_found")

    fields: dict[str, Any] = {}
    for key in ("label", "entrypoint", "domain_name", "notes"):
        if key in params and params[key] is not None:
            fields[key] = params[key]
    if "is_active" in params:
        fields["is_active"] = bool(params["is_active"])

    def _run():
        return _python_summary(svc(app, **fields))

    return run_service(_run)


@register_tool(
    name="delete_python_app",
    description="Supprime une application Python (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "app_id": {"type": "integer"},
            "remove_files": {"type": "boolean"},
        },
        "required": ["app_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_python_app(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.python_apps.services import apps_qs, delete_python_app as svc

    app = apps_qs(user).filter(pk=require_int(params, "app_id")).first()
    if not app:
        return err("Application Python introuvable", "not_found")
    name = app.name

    def _run():
        svc(app, remove_files=bool(params.get("remove_files", False)))
        return {"deleted": name}

    return run_service(_run)


@register_tool(
    name="create_node_app",
    description="Crée une application Node.js (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "label": {"type": "string"},
            "node_version": {"type": "string"},
            "framework": {"type": "string"},
            "relative_root": {"type": "string"},
            "start_script": {"type": "string"},
            "entrypoint": {"type": "string"},
            "domain_name": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_node_app(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.node_apps.models import NodeApp
    from apps.node_apps.services import create_node_app as svc

    name = require_str(params, "name", max_len=64)
    if not name:
        return err("name requis")

    def _run():
        app = svc(
            owner=user,
            name=name,
            label=require_str(params, "label", max_len=120),
            node_version=require_str(params, "node_version", default="20") or "20",
            framework=require_str(params, "framework", default=NodeApp.Framework.GENERIC)
            or NodeApp.Framework.GENERIC,
            relative_root=require_str(params, "relative_root", max_len=500),
            start_script=require_str(params, "start_script", default="start") or "start",
            entrypoint=require_str(params, "entrypoint", default="server.js") or "server.js",
            domain_name=require_str(params, "domain_name", max_len=253),
            notes=require_str(params, "notes", max_len=200),
        )
        return _node_summary(app)

    return run_service(_run)


@register_tool(
    name="update_node_app",
    description="Met à jour une application Node.js (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "app_id": {"type": "integer"},
            "label": {"type": "string"},
            "start_script": {"type": "string"},
            "entrypoint": {"type": "string"},
            "domain_name": {"type": "string"},
            "notes": {"type": "string"},
            "is_active": {"type": "boolean"},
        },
        "required": ["app_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def update_node_app(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.node_apps.services import apps_qs, update_node_app as svc

    app = apps_qs(user).filter(pk=require_int(params, "app_id")).first()
    if not app:
        return err("Application Node introuvable", "not_found")

    fields: dict[str, Any] = {}
    for key in ("label", "start_script", "entrypoint", "domain_name", "notes"):
        if key in params and params[key] is not None:
            fields[key] = params[key]
    if "is_active" in params:
        fields["is_active"] = bool(params["is_active"])

    def _run():
        return _node_summary(svc(app, **fields))

    return run_service(_run)


@register_tool(
    name="delete_node_app",
    description="Supprime une application Node.js (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "app_id": {"type": "integer"},
            "remove_files": {"type": "boolean"},
        },
        "required": ["app_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_node_app(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.node_apps.services import apps_qs, delete_node_app as svc

    app = apps_qs(user).filter(pk=require_int(params, "app_id")).first()
    if not app:
        return err("Application Node introuvable", "not_found")
    name = app.name

    def _run():
        svc(app, remove_files=bool(params.get("remove_files", False)))
        return {"deleted": name}

    return run_service(_run)
