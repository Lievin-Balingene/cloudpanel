"""Handlers tools — wrappers autour des services V-zone existants."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Any

from django.conf import settings

from apps.accounts.models import User
from apps.ai_assistant.services.redaction import redact_obj, redact_text, strip_prompt_injection
from apps.ai_assistant.tools import register_tool
from apps.core.exceptions import VZoneAPIException


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, **data}


def _err(message: str, code: str = "tool_error") -> dict[str, Any]:
    return {"ok": False, "error": message, "code": code}


def _owned_python(user: User, app_id: int | None):
    from apps.python_apps.services import apps_qs

    qs = apps_qs(user)
    if app_id:
        return qs.filter(pk=app_id).first()
    return qs.order_by("-updated_at").first()


def _owned_node(user: User, app_id: int | None):
    from apps.node_apps.services import apps_qs

    qs = apps_qs(user)
    if app_id:
        return qs.filter(pk=app_id).first()
    return qs.order_by("-updated_at").first()


@register_tool(
    name="get_server_info",
    description="Informations panel non sensibles (version, modules, modes provision).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def get_server_info(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from vzone import __version__

    return _ok(
        {
            "panel_version": __version__,
            "python": sys.version.split()[0],
            "ai_provider": getattr(settings, "VZONE_AI_PROVIDER", "auto"),
            "provision": {
                "python": getattr(settings, "VZONE_PYTHON_PROVISION_MODE", "auto"),
                "node": getattr(settings, "VZONE_NODE_PROVISION_MODE", "auto"),
                "git": getattr(settings, "VZONE_GIT_PROVISION_MODE", "auto"),
            },
            "user": {
                "username": user.username,
                "role": getattr(user, "role", ""),
            },
        }
    )


@register_tool(
    name="get_deployment_context",
    description="Contexte déploiement du compte : apps Python/Node, dépôts Git, domaines (sans secrets).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def get_deployment_context(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.ai_assistant.services.context import build_user_context

    return _ok({"context": build_user_context(user)})


@register_tool(
    name="check_python_version",
    description="Liste les interpréteurs Python détectés sur le serveur.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def check_python_version(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del user, params
    found = []
    for candidate in ("python3.12", "python3.11", "python3.10", "python3.9", "python3"):
        path = shutil.which(candidate)
        if path:
            found.append({"binary": candidate, "path": path})
    return _ok({"interpreters": found or [{"binary": "python3", "path": sys.executable}]})


@register_tool(
    name="check_node_version",
    description="Détecte Node.js / npm disponibles.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def check_node_version(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del user, params
    node = shutil.which("node")
    npm = shutil.which("npm")
    version = ""
    if node:
        try:
            version = subprocess.run(
                [node, "-v"], capture_output=True, text=True, timeout=5, check=False
            ).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            version = ""
    return _ok({"node": node or "", "npm": npm or "", "version": version})


@register_tool(
    name="check_database",
    description="Aperçu des bases du compte (noms uniquement, pas de mots de passe).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def check_database(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    try:
        from apps.databases.services import overview_for

        return _ok({"databases": overview_for(user)})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@register_tool(
    name="get_deployment_logs",
    description="Lit les derniers logs d'une app Python ou Node du compte.",
    parameters={
        "type": "object",
        "properties": {
            "runtime": {"type": "string", "enum": ["python", "node"]},
            "app_id": {"type": "integer"},
            "lines": {"type": "integer", "minimum": 10, "maximum": 200},
        },
        "additionalProperties": False,
    },
)
def get_deployment_logs(user: User, params: dict[str, Any]) -> dict[str, Any]:
    runtime = str(params.get("runtime") or "python").lower()
    app_id = params.get("app_id")
    lines = int(params.get("lines") or 100)
    lines = max(10, min(200, lines))
    if runtime == "node":
        from apps.node_apps.services import read_logs

        app = _owned_node(user, int(app_id) if app_id else None)
        if not app:
            return _err("Aucune application Node trouvée.", "not_found")
        raw = read_logs(app, lines=lines)
    else:
        from apps.python_apps.services import read_logs

        app = _owned_python(user, int(app_id) if app_id else None)
        if not app:
            return _err("Aucune application Python trouvée.", "not_found")
        raw = read_logs(app, lines=lines)
    cleaned = redact_obj(raw)
    if isinstance(cleaned, dict):
        for key in ("error", "access", "stdout", "stderr", "content", "tail"):
            if key in cleaned and isinstance(cleaned[key], str):
                cleaned[key] = strip_prompt_injection(redact_text(cleaned[key]))
    return _ok(
        {
            "runtime": runtime,
            "app_id": getattr(app, "pk", None),
            "app_name": getattr(app, "name", ""),
            "logs": cleaned,
        }
    )


@register_tool(
    name="analyze_deployment_error",
    description="Analyse heuristique des logs d'erreur (ModuleNotFound, port, permission…).",
    parameters={
        "type": "object",
        "properties": {
            "runtime": {"type": "string", "enum": ["python", "node"]},
            "app_id": {"type": "integer"},
        },
        "additionalProperties": False,
    },
)
def analyze_deployment_error(user: User, params: dict[str, Any]) -> dict[str, Any]:
    logs_result = get_deployment_logs(
        user, {**params, "lines": 120, "runtime": params.get("runtime") or "python"}
    )
    if not logs_result.get("ok"):
        return logs_result
    blob = json.dumps(logs_result.get("logs") or {}, ensure_ascii=False)
    blob = strip_prompt_injection(redact_text(blob))
    findings: list[dict[str, str]] = []

    patterns = [
        (
            r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]",
            "module_missing",
            "Module Python manquant",
            "Installez les dépendances (pip install -r requirements.txt) puis redémarrez.",
        ),
        (
            r"Address already in use|EADDRINUSE",
            "port_in_use",
            "Port déjà utilisé",
            "Arrêtez l'ancienne instance ou changez le port de l'application.",
        ),
        (
            r"Permission denied|EACCES",
            "permission",
            "Permission refusée",
            "Vérifiez les droits du home / fichiers de l'app (propriétaire = compte client).",
        ),
        (
            r"Can\'t connect to MySQL|could not connect to server|OperationalError",
            "database",
            "Connexion base de données",
            "Vérifiez host/user/db (pas le mot de passe dans le chat) et que la DB existe.",
        ),
        (
            r"SyntaxError|IndentationError",
            "syntax",
            "Erreur de syntaxe",
            "Corrigez le fichier indiqué dans la traceback.",
        ),
        (
            r"npm ERR!|Cannot find module",
            "node_deps",
            "Dépendances Node manquantes",
            "Exécutez npm install puis redémarrez l'app Node.",
        ),
    ]
    import re

    for pattern, code, title, fix in patterns:
        m = re.search(pattern, blob)
        if m:
            detail = m.group(0)
            if m.lastindex:
                detail = m.group(0)
            findings.append(
                {
                    "code": code,
                    "problem": title,
                    "evidence": detail[:240],
                    "likely_cause": title,
                    "suggested_fix": fix,
                    "suggested_action": (
                        "install_dependencies"
                        if code in {"module_missing", "node_deps"}
                        else "restart_application"
                        if code == "port_in_use"
                        else "manual"
                    ),
                }
            )
    if not findings:
        findings.append(
            {
                "code": "unknown",
                "problem": "Erreur non classifiée",
                "evidence": blob[-400:],
                "likely_cause": "Voir les logs complets",
                "suggested_fix": "Partagez le message d'erreur exact ou relancez l'app.",
                "suggested_action": "manual",
            }
        )
    return _ok(
        {
            "app_id": logs_result.get("app_id"),
            "app_name": logs_result.get("app_name"),
            "findings": findings,
            "primary": findings[0],
        }
    )


@register_tool(
    name="check_domain_configuration",
    description="Liste les domaines du compte et leur configuration basique.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def check_domain_configuration(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    try:
        from apps.domains.models import Domain

        qs = Domain.objects.all()
        if user.role == User.Role.CLIENT:
            qs = qs.filter(owner=user)
        elif user.role == User.Role.RESELLER:
            from django.db.models import Q

            qs = qs.filter(Q(owner=user) | Q(owner__parent=user))
        items = []
        for d in qs.order_by("name")[:50]:
            has_ssl = False
            try:
                has_ssl = bool(getattr(d, "ssl", None))
            except Exception:  # noqa: BLE001
                has_ssl = False
            items.append(
                {
                    "id": d.pk,
                    "name": d.name,
                    "document_root": getattr(d, "document_root", "") or "",
                    "ssl": has_ssl,
                }
            )
        return _ok({"domains": items, "count": len(items)})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@register_tool(
    name="check_web_server",
    description="Indique la stack web configurée (nginx/OLS) sans commandes shell libres.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def check_web_server(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del user, params
    return _ok(
        {
            "web_stack": getattr(settings, "VZONE_WEB_STACK", "auto"),
            "ols_enabled": getattr(settings, "VZONE_OLS_ENABLED", "auto"),
            "ols_default_engine": getattr(settings, "VZONE_OLS_DEFAULT_ENGINE", True),
        }
    )


@register_tool(
    name="check_application_status",
    description="Statut des applications Python et Node du compte.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def check_application_status(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.node_apps.services import overview_for as node_overview
    from apps.python_apps.services import overview_for as py_overview

    py_apps = []
    try:
        from apps.python_apps.services import apps_qs

        for a in apps_qs(user)[:30]:
            py_apps.append(
                {
                    "id": a.pk,
                    "name": a.name,
                    "status": a.status,
                    "port": a.port,
                    "domain": getattr(a, "domain_name", "") or "",
                    "last_error": redact_text(getattr(a, "last_error", "") or "", max_len=300),
                }
            )
    except Exception:  # noqa: BLE001
        pass
    node_apps = []
    try:
        from apps.node_apps.services import apps_qs

        for a in apps_qs(user)[:30]:
            node_apps.append(
                {
                    "id": a.pk,
                    "name": a.name,
                    "status": a.status,
                    "port": a.port,
                    "last_error": redact_text(getattr(a, "last_error", "") or "", max_len=300),
                }
            )
    except Exception:  # noqa: BLE001
        pass
    return _ok(
        {
            "python_overview": py_overview(user),
            "node_overview": node_overview(user),
            "python_apps": py_apps,
            "node_apps": node_apps,
        }
    )


@register_tool(
    name="restart_application",
    description="Redémarre une application Python ou Node (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "runtime": {"type": "string", "enum": ["python", "node"]},
            "app_id": {"type": "integer"},
        },
        "required": ["runtime", "app_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def restart_application(user: User, params: dict[str, Any]) -> dict[str, Any]:
    runtime = str(params.get("runtime") or "").lower()
    app_id = int(params.get("app_id") or 0)
    if not app_id:
        return _err("app_id requis", "invalid_params")
    try:
        if runtime == "node":
            from apps.node_apps.services import restart_node_app

            app = _owned_node(user, app_id)
            if not app:
                return _err("App Node introuvable", "not_found")
            app = restart_node_app(app)
        else:
            from apps.python_apps.services import restart_python_app

            app = _owned_python(user, app_id)
            if not app:
                return _err("App Python introuvable", "not_found")
            app = restart_python_app(app)
        return _ok({"app_id": app.pk, "name": app.name, "status": app.status})
    except VZoneAPIException as exc:
        return _err(str(exc.detail), getattr(exc, "default_code", "error") or "error")
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@register_tool(
    name="install_dependencies",
    description="Installe les dépendances (pip/npm) d'une app (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "runtime": {"type": "string", "enum": ["python", "node"]},
            "app_id": {"type": "integer"},
        },
        "required": ["runtime", "app_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def install_dependencies(user: User, params: dict[str, Any]) -> dict[str, Any]:
    runtime = str(params.get("runtime") or "").lower()
    app_id = int(params.get("app_id") or 0)
    try:
        if runtime == "node":
            from apps.node_apps.services import npm_install

            app = _owned_node(user, app_id)
            if not app:
                return _err("App Node introuvable", "not_found")
            result = npm_install(app)
        else:
            from apps.python_apps.services import install_requirements

            app = _owned_python(user, app_id)
            if not app:
                return _err("App Python introuvable", "not_found")
            result = install_requirements(app)
        return _ok(redact_obj(result if isinstance(result, dict) else {"result": str(result)}))
    except VZoneAPIException as exc:
        return _err(str(exc.detail))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@register_tool(
    name="deploy_application",
    description=(
        "Déploie via Git pull (+ script) pour un dépôt du compte. Confirmation requise. "
        "Ne clone pas d'URL arbitraire non enregistrée."
    ),
    parameters={
        "type": "object",
        "properties": {
            "repository_id": {"type": "integer"},
        },
        "required": ["repository_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def deploy_application(user: User, params: dict[str, Any]) -> dict[str, Any]:
    repo_id = int(params.get("repository_id") or 0)
    try:
        from apps.git_deploy.services import pull_repository, repos_qs

        repo = repos_qs(user).filter(pk=repo_id).first()
        if not repo:
            return _err("Dépôt Git introuvable", "not_found")
        repo = pull_repository(repo)
        return _ok(
            {
                "repository_id": repo.pk,
                "name": repo.name,
                "status": repo.status,
                "last_commit": repo.last_commit,
                "last_error": redact_text(repo.last_error or "", max_len=400),
            }
        )
    except VZoneAPIException as exc:
        return _err(str(exc.detail))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


def _slug_from_name(name: str) -> str:
    import re

    slug = (name or "").strip().lower().replace(" ", "-")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,47}", slug):
        raise VZoneAPIException(
            detail="Nom d'app invalide.",
            code="invalid_name",
            status_code=400,
        )
    return slug


@register_tool(
    name="create_python_app_from_git",
    description=(
        "Clone un dépôt Git (URL validée) puis crée une app Python pointant vers ce chemin. "
        "Confirmation requise. N'accepte pas de secrets dans env_vars (noms seulement)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "remote_url": {"type": "string"},
            "branch": {"type": "string"},
            "python_version": {"type": "string"},
            "framework": {"type": "string", "enum": ["django", "flask", "fastapi", "generic"]},
            "domain_name": {"type": "string"},
            "env_var_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Noms de variables uniquement (valeurs vides).",
            },
        },
        "required": ["name", "remote_url"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_python_app_from_git(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.git_deploy.services import create_repository
    from apps.python_apps.models import PythonApp
    from apps.python_apps.services import create_python_app, install_requirements
    from apps.security.git_safe import validate_git_branch, validate_git_remote_url

    try:
        name = _slug_from_name(str(params.get("name") or ""))
        remote_url = validate_git_remote_url(str(params.get("remote_url") or ""))
        branch = validate_git_branch(str(params.get("branch") or "main"))
        python_version = str(params.get("python_version") or "3.12").strip() or "3.12"
        framework = str(params.get("framework") or "django").lower()
        if framework not in PythonApp.Framework.values:
            framework = PythonApp.Framework.DJANGO
        domain_name = str(params.get("domain_name") or "").strip()
        env_vars: dict[str, str] = {}
        for raw in (params.get("env_var_names") or [])[:40]:
            key = str(raw).strip()
            if key and key.replace("_", "").isalnum():
                env_vars[key] = ""

        rel = f"repositories/{name}"
        repo = create_repository(
            owner=user,
            name=name,
            remote_url=remote_url,
            branch=branch,
            relative_path=rel,
            clone_now=True,
            label=name,
        )
        app = create_python_app(
            owner=user,
            name=name,
            python_version=python_version,
            framework=framework,
            relative_root=repo.relative_path,
            domain_name=domain_name,
            env_vars=env_vars,
            notes="Créé via AI Deployment Assistant",
        )
        deps: dict[str, Any] = {}
        try:
            deps = install_requirements(app)
        except Exception as exc:  # noqa: BLE001
            deps = {"ok": False, "error": str(exc)[:300]}

        return _ok(
            {
                "repository_id": repo.pk,
                "app_id": app.pk,
                "app_name": app.name,
                "status": app.status,
                "port": app.port,
                "relative_root": app.relative_root,
                "domain": app.domain_name,
                "deps": redact_obj(deps),
                "next": "Confirmez restart_application si besoin, puis testez le domaine.",
            }
        )
    except VZoneAPIException as exc:
        return _err(str(exc.detail), getattr(exc, "default_code", "error") or "error")
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@register_tool(
    name="create_node_app_from_git",
    description=(
        "Clone un dépôt Git puis crée une app Node.js. Confirmation requise. "
        "env_var_names = noms seulement."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "remote_url": {"type": "string"},
            "branch": {"type": "string"},
            "start_script": {"type": "string"},
            "domain_name": {"type": "string"},
            "env_var_names": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name", "remote_url"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_node_app_from_git(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.git_deploy.services import create_repository
    from apps.node_apps.services import create_node_app, npm_install
    from apps.security.git_safe import validate_git_branch, validate_git_remote_url

    try:
        name = _slug_from_name(str(params.get("name") or ""))
        remote_url = validate_git_remote_url(str(params.get("remote_url") or ""))
        branch = validate_git_branch(str(params.get("branch") or "main"))
        start_script = str(params.get("start_script") or "start").strip() or "start"
        domain_name = str(params.get("domain_name") or "").strip()
        env_vars: dict[str, str] = {}
        for raw in (params.get("env_var_names") or [])[:40]:
            key = str(raw).strip()
            if key and key.replace("_", "").isalnum():
                env_vars[key] = ""

        rel = f"repositories/{name}"
        repo = create_repository(
            owner=user,
            name=name,
            remote_url=remote_url,
            branch=branch,
            relative_path=rel,
            clone_now=True,
            label=name,
        )
        app = create_node_app(
            owner=user,
            name=name,
            relative_root=repo.relative_path,
            start_script=start_script,
            domain_name=domain_name,
            env_vars=env_vars,
            notes="Créé via AI Deployment Assistant",
        )
        deps: dict[str, Any] = {}
        try:
            deps = npm_install(app)
        except Exception as exc:  # noqa: BLE001
            deps = {"ok": False, "error": str(exc)[:300]}

        return _ok(
            {
                "repository_id": repo.pk,
                "app_id": app.pk,
                "app_name": app.name,
                "status": app.status,
                "port": app.port,
                "deps": redact_obj(deps),
            }
        )
    except VZoneAPIException as exc:
        return _err(str(exc.detail), getattr(exc, "default_code", "error") or "error")
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))
