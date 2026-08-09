"""Tools gestionnaire de fichiers (home jail)."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, require_int, require_str, run_service


def _paths_list(params: dict[str, Any], key: str = "paths") -> list[str]:
    raw = params.get(key)
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [str(p).strip() for p in raw if str(p).strip()]
    return []


def _entry_dict(entry: Any) -> dict[str, Any]:
    if hasattr(entry, "__dataclass_fields__"):
        return asdict(entry)
    if isinstance(entry, dict):
        return entry
    return {"repr": str(entry)}


@register_tool(
    name="list_files",
    description="Liste le contenu d'un dossier relatif au home du compte.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Chemin relatif (vide = racine home)"}},
        "additionalProperties": False,
    },
)
def list_files(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import list_directory

    path = require_str(params, "path", max_len=500) or None

    def _run():
        data = list_directory(user, path)
        # Ne pas exposer le chemin absolu serveur
        data.pop("root", None)
        entries = data.get("entries") or []
        return {"cwd": data.get("cwd", ""), "entries": entries[:200], "count": len(entries)}

    return run_service(_run)


@register_tool(
    name="read_file_content",
    description="Lit un fichier texte relatif au home (contenu tronqué à 8000 caractères).",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    },
)
def read_file_content(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import read_file

    path = require_str(params, "path", max_len=500)
    if not path:
        return err("path requis")

    def _run():
        data = read_file(user, path)
        content = str(data.get("content") or "")
        truncated = len(content) > 8000
        return {
            "path": data.get("path", path),
            "encoding": data.get("encoding"),
            "size": data.get("size"),
            "is_text": data.get("is_text"),
            "truncated": truncated,
            "content": content[:8000],
        }

    return run_service(_run)


@register_tool(
    name="search_account_files",
    description="Recherche des fichiers par nom dans le home (ou un sous-dossier).",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "path": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)
def search_account_files(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import search_files

    query = require_str(params, "query", max_len=200)
    if not query:
        return err("query requis")
    path = require_str(params, "path", max_len=500) or None
    limit = require_int(params, "limit") or 50
    limit = max(1, min(limit, 200))

    def _run():
        results = search_files(user, query, path, limit=limit)
        return {"query": query, "results": results, "count": len(results)}

    return run_service(_run)


@register_tool(
    name="mkdir_path",
    description="Crée un dossier relatif au home (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Chemin relatif complet du dossier à créer"},
            "parent": {"type": "string"},
            "name": {"type": "string"},
        },
        "additionalProperties": False,
    },
    dangerous=True,
)
def mkdir_path(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import mkdir

    parent = require_str(params, "parent", max_len=500)
    name = require_str(params, "name", max_len=255)
    if not name:
        full = require_str(params, "path", max_len=500).replace("\\", "/").strip("/")
        if not full:
            return err("path ou parent+name requis")
        if "/" in full:
            parent, name = full.rsplit("/", 1)
        else:
            parent, name = "", full

    def _run():
        entry = mkdir(user, parent, name)
        return _entry_dict(entry)

    return run_service(_run)


@register_tool(
    name="write_file",
    description="Écrit / crée un fichier texte relatif au home (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def write_file(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import write_file as svc

    path = require_str(params, "path", max_len=500)
    if not path:
        return err("path requis")
    content = str(params.get("content") if params.get("content") is not None else "")

    def _run():
        entry = svc(user, path, content)
        return _entry_dict(entry)

    return run_service(_run)


@register_tool(
    name="delete_paths",
    description="Supprime des fichiers/dossiers relatifs au home (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
        "required": ["paths"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_paths(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import delete_paths as svc

    paths = _paths_list(params)
    if not paths:
        return err("paths requis")

    def _run():
        count = svc(user, paths)
        return {"deleted_count": count, "paths": paths}

    return run_service(_run)


@register_tool(
    name="rename_path",
    description="Renomme un fichier/dossier dans le même dossier parent (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "new_name": {"type": "string"},
        },
        "required": ["path", "new_name"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def rename_path(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import rename_path as svc

    path = require_str(params, "path", max_len=500)
    new_name = require_str(params, "new_name", max_len=255)
    if not path or not new_name:
        return err("path et new_name requis")

    def _run():
        return _entry_dict(svc(user, path, new_name))

    return run_service(_run)


@register_tool(
    name="move_paths",
    description="Déplace des fichiers/dossiers vers un dossier destination (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "paths": {"type": "array", "items": {"type": "string"}},
            "destination": {"type": "string"},
        },
        "required": ["paths", "destination"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def move_paths(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import move_paths as svc

    paths = _paths_list(params)
    if not paths:
        return err("paths requis")
    if "destination" not in params:
        return err("destination requis")
    destination = require_str(params, "destination", max_len=500)

    def _run():
        entries = svc(user, paths, destination)
        return {"moved": [_entry_dict(e) for e in entries]}

    return run_service(_run)


@register_tool(
    name="copy_paths",
    description="Copie des fichiers/dossiers vers un dossier destination (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "paths": {"type": "array", "items": {"type": "string"}},
            "destination": {"type": "string"},
        },
        "required": ["paths", "destination"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def copy_paths(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import copy_paths as svc

    paths = _paths_list(params)
    if not paths:
        return err("paths requis")
    if "destination" not in params:
        return err("destination requis")
    destination = require_str(params, "destination", max_len=500)

    def _run():
        entries = svc(user, paths, destination)
        return {"copied": [_entry_dict(e) for e in entries]}

    return run_service(_run)


@register_tool(
    name="chmod_path",
    description="Change les permissions octales d'un chemin (ex: 644, 755) (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "mode": {"type": "string"},
        },
        "required": ["path", "mode"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def chmod_path(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import chmod_path as svc

    path = require_str(params, "path", max_len=500)
    mode = require_str(params, "mode", max_len=4)
    if not path or not mode:
        return err("path et mode requis")

    def _run():
        return _entry_dict(svc(user, path, mode))

    return run_service(_run)


@register_tool(
    name="compress_files",
    description="Crée une archive zip/tar.gz à partir de chemins relatifs (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "paths": {"type": "array", "items": {"type": "string"}},
            "archive_path": {"type": "string"},
            "format": {"type": "string", "enum": ["zip", "tar.gz", "tgz"]},
        },
        "required": ["paths", "archive_path"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def compress_files(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import compress

    paths = _paths_list(params)
    archive_path = require_str(params, "archive_path", max_len=500)
    fmt = require_str(params, "format", default="zip") or "zip"
    if not paths or not archive_path:
        return err("paths et archive_path requis")

    def _run():
        return _entry_dict(compress(user, paths, archive_path, fmt=fmt))

    return run_service(_run)


@register_tool(
    name="decompress_archive",
    description="Décompresse une archive zip/tar.gz dans un dossier (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "archive_path": {"type": "string"},
            "destination": {"type": "string"},
        },
        "required": ["archive_path"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def decompress_archive(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import decompress

    archive_path = require_str(params, "archive_path", max_len=500)
    if not archive_path:
        return err("archive_path requis")
    destination = require_str(params, "destination", max_len=500) or None

    def _run():
        return decompress(user, archive_path, destination)

    return run_service(_run)


@register_tool(
    name="inspect_project_folder",
    description=(
        "Analyse un dossier du home pour détecter le type de projet "
        "(Django, Flask, FastAPI, Node, etc.) via fichiers marqueurs."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Chemin relatif au home (ex. vzone). Vide = racine.",
            }
        },
        "additionalProperties": False,
    },
)
def inspect_project_folder(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.files.services import resolve_path
    from apps.python_apps.services import detect_django_project_package

    rel = require_str(params, "path", max_len=500)

    def _run():
        root = resolve_path(user, rel or None)
        if not root.exists():
            return {
                "ok": False,
                "error": f"Dossier introuvable : `{rel or '/'}`",
                "code": "not_found",
            }
        if not root.is_dir():
            return {
                "ok": False,
                "error": f"`{rel}` n'est pas un dossier",
                "code": "not_a_directory",
            }

        names: set[str] = set()
        dirs: list[str] = []
        files: list[str] = []
        try:
            for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if child.name.startswith("."):
                    continue
                names.add(child.name.lower())
                if child.is_dir():
                    dirs.append(child.name)
                elif child.is_file():
                    files.append(child.name)
        except OSError as exc:
            return {"ok": False, "error": str(exc), "code": "fs_error"}

        markers = {
            "manage.py": "manage.py" in names,
            "passenger_wsgi.py": "passenger_wsgi.py" in names,
            "wsgi.py": "wsgi.py" in names or any(
                (root / d / "wsgi.py").is_file() for d in dirs[:20]
            ),
            "asgi.py": "asgi.py" in names or any(
                (root / d / "asgi.py").is_file() for d in dirs[:20]
            ),
            "requirements.txt": "requirements.txt" in names,
            "pyproject.toml": "pyproject.toml" in names,
            "package.json": "package.json" in names,
            "app.py": "app.py" in names,
            "main.py": "main.py" in names,
            "dockerfile": "dockerfile" in names,
        }

        req_hint = ""
        req_path = root / "requirements.txt"
        if req_path.is_file():
            try:
                req_hint = req_path.read_text(encoding="utf-8", errors="ignore")[:2000].lower()
            except OSError:
                req_hint = ""

        framework = "unknown"
        mode = "wsgi"
        runtime = "python"
        confidence = 0.35
        signals: list[str] = []

        if markers["manage.py"] or "django" in req_hint:
            framework = "django"
            mode = "wsgi"
            confidence = 0.95 if markers["manage.py"] else 0.75
            signals.append("manage.py" if markers["manage.py"] else "django in requirements")
        elif "fastapi" in req_hint or (
            markers["asgi.py"] and ("fastapi" in req_hint or "uvicorn" in req_hint)
        ):
            framework = "fastapi"
            mode = "asgi"
            confidence = 0.85
            signals.append("fastapi/asgi")
        elif "flask" in req_hint or (markers["app.py"] and "flask" in req_hint):
            framework = "flask"
            mode = "wsgi"
            confidence = 0.8
            signals.append("flask")
        elif markers["package.json"]:
            framework = "node"
            mode = "node"
            runtime = "node"
            confidence = 0.9
            signals.append("package.json")
        elif markers["requirements.txt"] or markers["pyproject.toml"] or markers["main.py"]:
            framework = "generic"
            mode = "asgi" if markers["asgi.py"] else "wsgi"
            confidence = 0.55
            signals.append("python project files")

        django_package = ""
        if framework == "django":
            try:
                django_package = detect_django_project_package(root)
            except Exception:  # noqa: BLE001
                django_package = ""

        entrypoint = "passenger_wsgi.py"
        if framework == "fastapi" or mode == "asgi":
            entrypoint = "asgi:application"
        elif framework == "flask":
            entrypoint = "passenger_wsgi.py"
        elif runtime == "node":
            entrypoint = "server.js"

        return {
            "path": rel or "",
            "exists": True,
            "framework": framework,
            "runtime": runtime,
            "mode": mode,
            "confidence": confidence,
            "signals": signals,
            "markers": markers,
            "django_package": django_package,
            "entrypoint_suggested": entrypoint,
            "has_requirements": markers["requirements.txt"],
            "has_package_json": markers["package.json"],
            "top_dirs": dirs[:30],
            "top_files": files[:40],
            "summary": (
                f"{framework} ({runtime}/{mode})"
                if framework != "unknown"
                else "type de projet non déterminé"
            ),
        }

    return run_service(_run)
