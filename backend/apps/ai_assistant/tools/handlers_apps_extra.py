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
    from apps.ai_assistant.tools.helpers import ai_python_apps_qs as apps_qs
    from apps.python_apps.services import update_python_app as svc

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
    from apps.ai_assistant.tools.helpers import ai_python_apps_qs as apps_qs
    from apps.python_apps.services import delete_python_app as svc

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
    from apps.ai_assistant.tools.helpers import ai_node_apps_qs as apps_qs
    from apps.node_apps.services import update_node_app as svc

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
    from apps.ai_assistant.tools.helpers import ai_node_apps_qs as apps_qs
    from apps.node_apps.services import delete_node_app as svc

    app = apps_qs(user).filter(pk=require_int(params, "app_id")).first()
    if not app:
        return err("Application Node introuvable", "not_found")
    name = app.name

    def _run():
        svc(app, remove_files=bool(params.get("remove_files", False)))
        return {"deleted": name}

    return run_service(_run)


@register_tool(
    name="sync_python_passenger_wsgi",
    description=(
        "Réécrit passenger_wsgi.py d'une app Python/Django pour pointer vers le bon "
        "package settings (corrige le stub « Hello from V-zone Python app »)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "app_id": {"type": "integer"},
            "force": {
                "type": "boolean",
                "description": "Toujours réécrire (sinon seulement stub Hello / mauvais settings).",
            },
            "restart": {
                "type": "boolean",
                "description": "Redémarrer l'app après sync (recommandé).",
            },
        },
        "required": ["app_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def sync_python_passenger_wsgi(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.ai_assistant.tools.helpers import ai_python_apps_qs as apps_qs
    from apps.python_apps.services import start_python_app, stop_python_app, sync_passenger_wsgi

    app = apps_qs(user).filter(pk=require_int(params, "app_id")).first()
    if not app:
        return err("Application Python introuvable", "not_found")
    force = bool(params.get("force", False))
    do_restart = bool(params.get("restart", True))

    def _run():
        info = sync_passenger_wsgi(app, force=force)
        restarted = False
        if do_restart:
            try:
                stop_python_app(app)
            except Exception:  # noqa: BLE001
                pass
            start_python_app(app)
            restarted = True
        return {**info, "app": _python_summary(app), "restarted": restarted}

    return run_service(_run)


@register_tool(
    name="add_django_page",
    description=(
        "Ajoute une page Django dynamique (vue + template + URL) ET le bouton dans le menu "
        "de navigation du site (base.html / navbar), ex. slug=lievin → /lievin/ + lien menu. "
        "Cible via app_id ou app_name (ex: vzone). Redémarre l'app. "
        "À utiliser aussi quand l'utilisateur dit « vas-y », « ajoute au menu », « bouton dans le menu »."
    ),
    parameters={
        "type": "object",
        "properties": {
            "app_id": {"type": "integer"},
            "app_name": {"type": "string", "description": "Nom de l'app (ex: vzone)"},
            "slug": {
                "type": "string",
                "description": "Slug URL (ex: lievin → /lievin/)",
            },
            "title": {"type": "string", "description": "Titre / libellé menu (défaut: slug)"},
            "restart": {
                "type": "boolean",
                "description": "Redémarrer l'app après écriture (défaut true)",
            },
            "add_to_nav": {
                "type": "boolean",
                "description": "Insérer le lien dans base.html / navbar (défaut true)",
            },
        },
        "required": ["slug"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def add_django_page(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.ai_assistant.tools.helpers import ai_python_apps_qs as apps_qs
    from apps.python_apps.services import add_django_dynamic_page as svc

    slug = require_str(params, "slug", max_len=40)
    if not slug:
        return err("slug requis (ex: lievin)")
    app_id = require_int(params, "app_id")
    app_name = require_str(params, "app_name", max_len=80)
    qs = apps_qs(user)
    app = None
    if app_id:
        app = qs.filter(pk=app_id).first()
    elif app_name:
        app = qs.filter(name__iexact=app_name.strip()).first()
    else:
        # Une seule app Django → cibler automatiquement
        django_apps = list(qs.filter(framework="django")[:3])
        if len(django_apps) == 1:
            app = django_apps[0]
        elif qs.count() == 1:
            app = qs.first()
    if not app:
        return err(
            "App Django introuvable — passez app_id ou app_name (ex: vzone).",
            "not_found",
        )

    def _run():
        return svc(
            app,
            slug=slug,
            title=require_str(params, "title", max_len=120) or "",
            restart=bool(params.get("restart", True)),
            add_to_nav=bool(params.get("add_to_nav", True)),
        )

    return run_service(_run)
