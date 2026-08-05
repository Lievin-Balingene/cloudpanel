"""Services applications Python : venv, configs, start/stop, requirements."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.files.services import user_home
from apps.python_apps.models import PythonApp

logger = logging.getLogger(__name__)


def _refresh_domain_routing(domain_name: str = "") -> None:
    """Priorité app → régénère les vhosts Nginx (ciblé si domain_name fourni)."""
    try:
        name = (domain_name or "").strip().lower()
        if name.startswith("www."):
            name = name[4:]
        if name:
            from apps.domains.models import Domain
            from apps.domains.vhosts import sync_domain_vhost

            domain = Domain.objects.filter(name__iexact=name).select_related("owner", "parent").first()
            if domain is None and not name.startswith("www."):
                domain = (
                    Domain.objects.filter(name__iexact=f"www.{name}")
                    .select_related("owner", "parent")
                    .first()
                )
            if domain is not None:
                sync_domain_vhost(domain)
                return
        from apps.domains.services import refresh_web_routing

        refresh_web_routing()
    except Exception:  # noqa: BLE001
        logger.debug("refresh_web_routing skip", exc_info=True)

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")

# Package Django créé par `django-admin startproject config .` (commande déployée au client).
DJANGO_PROJECT_PACKAGE = "config"

WSGI_TEMPLATE = '''\
"""Entrée WSGI générée par V-zone Panel (compatible cPanel / passenger_wsgi)."""
import os
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

os.environ["DJANGO_SETTINGS_MODULE"] = "{settings_module}"

try:
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()
except Exception:
    def application(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"Hello from V-zone Python app\\n"]
'''

ASGI_TEMPLATE = '''\
"""Entrée ASGI générée par V-zone Panel."""
import os
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

try:
    from fastapi import FastAPI
    application = FastAPI(title="V-zone Python App")

    @application.get("/")
    def root():
        return {"ok": True, "panel": "vzone"}
except Exception:
    async def application(scope, receive, send):
        if scope["type"] != "http":
            return
        await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"text/plain"]]})
        await send({"type": "http.response.body", "body": b"Hello from V-zone ASGI app\\n"})
'''

REQUIREMENTS_TEMPLATE = "# requirements.txt — V-zone Panel\n"
REQUIREMENTS_DJANGO = (
    "# requirements.txt — V-zone Panel (Django)\n"
    "Django>=5.0,<6\n"
    "gunicorn>=22.0\n"
)
REQUIREMENTS_FLASK = "# requirements.txt — V-zone Panel (Flask)\ngunicorn>=22.0\nFlask>=3.0\n"
REQUIREMENTS_FASTAPI = (
    "# requirements.txt — V-zone Panel (FastAPI)\n"
    "fastapi>=0.110\n"
    "uvicorn[standard]>=0.27\n"
)


def apps_qs(user: User) -> QuerySet[PythonApp]:
    qs = PythonApp.objects.select_related("owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def _assert_python_quota(owner: User) -> None:
    quota = getattr(owner, "quota", None)
    if quota is None:
        return
    limit = quota.python_apps
    if limit == 0 and owner.role == User.Role.ADMINISTRATOR:
        return
    used = PythonApp.objects.filter(owner=owner).count()
    if limit > 0 and used >= limit:
        raise QuotaExceeded(
            detail="Quota d'applications Python atteint.",
            extra={"limit": limit, "used": used},
        )


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_PYTHON_PROVISION_MODE", "auto").lower()
    return mode if mode in {"auto", "live", "mock"} else "auto"


def should_execute() -> bool:
    mode = provision_mode()
    if mode == "mock":
        return False
    if mode == "live":
        return True
    return True  # auto: try real ops when possible; fall back inside helpers


def config_root() -> Path:
    root = Path(getattr(settings, "VZONE_PYTHON_CONFIG_DIR", None) or (Path(settings.VZONE_DATA_ROOT) / "python_apps"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_app_root(owner: User, relative_root: str) -> tuple[str, Path]:
    rel = (relative_root or "").replace("\\", "/").strip("/")
    if not rel:
        raise VZoneAPIException(detail="Chemin applicatif requis.", code="invalid_root", status_code=400)
    if ".." in Path(rel).parts:
        raise VZoneAPIException(detail="Chemin invalide.", code="invalid_root", status_code=400)
    # Interdire de pointer le venv cPanel comme application root
    parts = Path(rel).parts
    if parts and parts[0] == "virtualenv":
        raise VZoneAPIException(
            detail="L'application root ne peut pas être sous virtualenv/ (réservé au venv).",
            code="invalid_root",
            status_code=400,
        )
    home = user_home(owner)
    target = (home / rel).resolve()
    try:
        target.relative_to(home)
    except ValueError as exc:
        raise VZoneAPIException(
            detail="Chemin hors du home autorisé.",
            code="path_forbidden",
            status_code=403,
        ) from exc
    return rel, target


def cpanel_venv_path(owner: User, app_name: str, python_version: str) -> Path:
    """Comme cPanel : ~/virtualenv/<app>/<python_version>/ (hors du projet Django)."""
    version = (python_version or "3.12").strip() or "3.12"
    return user_home(owner) / "virtualenv" / app_name / version


def detect_django_project_package(app_root: Path) -> str:
    """Trouve le package settings à côté de manage.py (même répertoire que passenger_wsgi)."""
    if (app_root / "manage.py").exists():
        for child in sorted(app_root.iterdir()):
            if not child.is_dir() or child.name.startswith(".") or child.name in {"static", "media", "logs", "public"}:
                continue
            if (child / "settings.py").exists():
                return child.name
    return DJANGO_PROJECT_PACKAGE


def allocate_port(owner: User) -> int:
    base = int(getattr(settings, "VZONE_PYTHON_PORT_BASE", 8100))
    used = set(PythonApp.objects.filter(port__gt=0).values_list("port", flat=True))
    for offset in range(0, 5000):
        candidate = base + offset
        if candidate not in used:
            return candidate
    raise VZoneAPIException(detail="Aucun port disponible.", code="no_port", status_code=503)


def python_binary(version: str) -> str:
    configured = getattr(settings, "VZONE_PYTHON_BIN", "") or ""
    if configured:
        return configured
    # Prefer exact version if present
    for candidate in (f"python{version}", f"python{version.split('.')[0]}", "python3", sys.executable):
        path = shutil.which(candidate) if candidate != sys.executable else candidate
        if path:
            return path
    return sys.executable


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            env=env,
            timeout=300,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        stderr = getattr(exc, "stderr", None) or str(exc)
        raise VZoneAPIException(
            detail="Échec commande Python.",
            code="python_cmd_failed",
            status_code=502,
            extra={"stderr": stderr, "cmd": cmd},
        ) from exc


def write_app_config(app: PythonApp) -> Path:
    root = config_root() / str(app.owner_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{app.name}.json"
    payload = {
        "id": app.pk,
        "owner": app.owner.username,
        "name": app.name,
        "mode": app.mode,
        "framework": app.framework,
        "root": app.relative_root,
        "venv": app.venv_path,
        "entrypoint": app.entrypoint,
        "port": app.port,
        "env": app.env_vars,
        "status": app.status,
        "pid": app.pid,
        "domain": app.domain_name,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _scaffold(app_root: Path, mode: str, framework: str) -> None:
    """
    Prépare l'application root à la création uniquement (comme cPanel) :
    passenger_wsgi.py / asgi.py / requirements.txt — jamais écrasés s'ils existent déjà.
    """
    app_root.mkdir(parents=True, exist_ok=True)
    (app_root / "logs").mkdir(exist_ok=True)
    req = app_root / "requirements.txt"
    if not req.exists():
        if framework == PythonApp.Framework.DJANGO:
            req.write_text(REQUIREMENTS_DJANGO, encoding="utf-8")
        elif framework == PythonApp.Framework.FLASK:
            req.write_text(REQUIREMENTS_FLASK, encoding="utf-8")
        elif framework == PythonApp.Framework.FASTAPI:
            req.write_text(REQUIREMENTS_FASTAPI, encoding="utf-8")
        else:
            req.write_text(REQUIREMENTS_TEMPLATE, encoding="utf-8")
    if mode == PythonApp.Mode.ASGI:
        entry = app_root / "asgi.py"
        if not entry.exists():
            entry.write_text(ASGI_TEMPLATE, encoding="utf-8")
    else:
        entry = app_root / "passenger_wsgi.py"
        # Comme cPanel : créer une seule fois — les modifications utilisateur sont préservées
        if not entry.exists():
            pkg = (
                detect_django_project_package(app_root)
                if framework == PythonApp.Framework.DJANGO
                else "project"
            )
            entry.write_text(
                WSGI_TEMPLATE.format(settings_module=f"{pkg}.settings"),
                encoding="utf-8",
            )
    readme = app_root / "README.vzone.md"
    if not readme.exists():
        readme.write_text(
            "# Application Python V-zone (style cPanel)\n\n"
            f"Mode: {mode}\nFramework: {framework}\n\n"
            "Le fichier `passenger_wsgi.py` est créé à la création de l'app uniquement.\n"
            "Vos modifications ne sont jamais écrasées par Start / Restart / Update.\n",
            encoding="utf-8",
        )


def absolute_app_root(app: PythonApp) -> Path:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    return app_root


def enter_command_for(app: PythonApp) -> str:
    """
    Une ligne à coller dans le terminal SSH (cPanel Application Manager) :
    source ~/virtualenv/<app>/<ver>/bin/activate && cd <application_root>
    """
    app_root = absolute_app_root(app)
    venv = Path(app.venv_path) if app.venv_path else cpanel_venv_path(app.owner, app.name, app.python_version)
    activate = venv / "bin" / "activate"
    return f"source {activate} && cd {app_root}"


def deploy_script_for(app: PythonApp) -> str:
    """Script multi-lignes à coller — projet Django + passenger_wsgi dans le même dossier."""
    app_root = absolute_app_root(app)
    enter = enter_command_for(app)
    pkg = detect_django_project_package(app_root)
    lines = [
        "# V-zone / cPanel — déployer dans l'Application root",
        "# passenger_wsgi.py et le projet Django sont dans LE MÊME répertoire.",
        enter,
        "pip install --upgrade pip",
        "pip install -r requirements.txt",
    ]
    if app.framework == PythonApp.Framework.DJANGO:
        lines.extend(
            [
                "# Créer le projet ICI (à côté de passenger_wsgi.py) si besoin :",
                f"if [ ! -f manage.py ]; then django-admin startproject {pkg} .; fi",
                f"# passenger_wsgi.py → DJANGO_SETTINGS_MODULE={pkg}.settings",
                "python manage.py migrate",
                "python manage.py collectstatic --noinput || true",
                "# Puis dans le panel : Start.",
            ]
        )
    elif app.framework == PythonApp.Framework.FLASK:
        lines.append("# Placez votre app Flask ici (même dossier), puis Start.")
    elif app.framework == PythonApp.Framework.FASTAPI:
        lines.append("# Placez asgi.py ici, puis Start.")
    else:
        lines.append("# Déposez votre code ici, puis Start.")
    if app.domain_name:
        lines.append(f"# Application URL / domaine : {app.domain_name}")
    lines.append(f"# Application root : {app_root}")
    lines.append(f"# passenger_wsgi.py : {app_root / 'passenger_wsgi.py'}")
    return "\n".join(lines) + "\n"


def deploy_info(app: PythonApp) -> dict:
    """Métadonnées affichées dans le panel (chemin + commandes à copier)."""
    app_root = absolute_app_root(app)
    venv = Path(app.venv_path) if app.venv_path else cpanel_venv_path(app.owner, app.name, app.python_version)
    enter = enter_command_for(app)
    script = deploy_script_for(app)
    pkg = (
        detect_django_project_package(app_root)
        if app.framework == PythonApp.Framework.DJANGO
        else ""
    )
    try:
        (app_root / "ENTER.sh").write_text(f"#!/usr/bin/env bash\n{enter}\n", encoding="utf-8")
        (app_root / "DEPLOY.sh").write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{script}", encoding="utf-8")
    except OSError:
        logger.debug("Impossible d'écrire ENTER.sh/DEPLOY.sh", exc_info=True)
    return {
        "absolute_root": str(app_root),
        "venv_path": str(venv),
        "enter_command": enter,
        "deploy_command": script,
        "passenger_wsgi": str(app_root / "passenger_wsgi.py")
        if app.mode == PythonApp.Mode.WSGI
        else "",
        "django_project": pkg,
        "home_path": str(user_home(app.owner)),
    }


def create_venv(venv_dir: Path, version: str) -> Path:
    """Crée le venv cPanel sous ~/virtualenv/<app>/<version>/."""
    if provision_mode() == "mock" or not should_execute():
        venv_dir.mkdir(parents=True, exist_ok=True)
        (venv_dir / "bin").mkdir(exist_ok=True)
        marker = venv_dir / "pyvenv.cfg"
        marker.write_text(f"home = mock\nversion = {version}\n", encoding="utf-8")
        return venv_dir
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    if not (venv_dir / "pyvenv.cfg").exists():
        py = python_binary(version)
        _run([py, "-m", "venv", str(venv_dir)])
    return venv_dir


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


@transaction.atomic
def create_python_app(
    *,
    owner: User,
    name: str,
    label: str = "",
    python_version: str = "3.12",
    mode: str = PythonApp.Mode.WSGI,
    framework: str = PythonApp.Framework.GENERIC,
    relative_root: str = "",
    entrypoint: str = "",
    domain_name: str = "",
    env_vars: dict | None = None,
    notes: str = "",
) -> PythonApp:
    slug = name.strip().lower().replace(" ", "-")
    if not NAME_RE.match(slug):
        raise VZoneAPIException(
            detail="Nom d'app invalide (a-z, 0-9, _-).",
            code="invalid_name",
            status_code=400,
        )
    if mode not in PythonApp.Mode.values:
        raise VZoneAPIException(detail="Mode invalide.", code="invalid_mode", status_code=400)
    if framework not in PythonApp.Framework.values:
        raise VZoneAPIException(detail="Framework invalide.", code="invalid_framework", status_code=400)
    _assert_python_quota(owner)
    if PythonApp.objects.filter(owner=owner, name=slug).exists():
        raise VZoneAPIException(detail="Cette application existe déjà.", code="exists", status_code=400)

    if framework == PythonApp.Framework.DJANGO:
        # Comme cPanel : Django = WSGI + passenger_wsgi.py dans l'application root.
        mode = PythonApp.Mode.WSGI

    # Application root = chemin du projet (cPanel). Défaut = nom de l'app (PAS apps/…).
    rel = relative_root.strip().replace("\\", "/").strip("/")
    if not rel:
        if framework == PythonApp.Framework.DJANGO:
            raise VZoneAPIException(
                detail="Indiquez l'Application root (chemin du projet Django), comme sur cPanel.",
                code="application_root_required",
                status_code=400,
            )
        rel = slug

    rel, app_root = resolve_app_root(owner, rel)
    _scaffold(app_root, mode, framework)
    venv_dir = create_venv(cpanel_venv_path(owner, slug, python_version), python_version)

    if not entrypoint:
        entrypoint = "asgi:application" if mode == PythonApp.Mode.ASGI else "passenger_wsgi.py"

    app = PythonApp.objects.create(
        owner=owner,
        name=slug,
        label=label or slug,
        python_version=python_version,
        mode=mode,
        framework=framework,
        relative_root=rel,
        entrypoint=entrypoint,
        port=allocate_port(owner),
        env_vars=env_vars or {},
        venv_path=str(venv_dir),
        domain_name=normalize_app_domain(domain_name),
        notes=notes,
        status=PythonApp.Status.STOPPED,
    )
    write_app_config(app)
    deploy_info(app)
    _refresh_domain_routing(app.domain_name)
    return app


@transaction.atomic
def update_python_app(
    app: PythonApp,
    *,
    label: str | None = None,
    entrypoint: str | None = None,
    domain_name: str | None = None,
    env_vars: dict | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
) -> PythonApp:
    old_domain = app.domain_name
    if label is not None:
        app.label = label
    if entrypoint is not None:
        app.entrypoint = entrypoint
    if domain_name is not None:
        app.domain_name = normalize_app_domain(domain_name)
    if env_vars is not None:
        app.env_vars = env_vars
    if notes is not None:
        app.notes = notes
    if is_active is not None:
        app.is_active = is_active
    app.save()
    write_app_config(app)
    # Re-proxifier l'ancien domaine (retour public_html) + le nouveau (vers l'app).
    if domain_name is not None and old_domain and old_domain != app.domain_name:
        _refresh_domain_routing(old_domain)
    _refresh_domain_routing(app.domain_name)
    return app


def install_requirements(app: PythonApp) -> dict:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    req = app_root / (app.requirements_file or "requirements.txt")
    if not req.exists():
        raise VZoneAPIException(detail="requirements.txt introuvable.", code="no_requirements", status_code=400)
    venv_dir = Path(app.venv_path) if app.venv_path else cpanel_venv_path(app.owner, app.name, app.python_version)
    py = venv_python(venv_dir)
    if provision_mode() == "mock" or not py.exists():
        log = app_root / "logs" / "pip.log"
        log.write_text(f"mock install -r {req.name}\n", encoding="utf-8")
        return {"mode": "mock", "requirements": str(req), "log": str(log)}
    result = _run([str(py), "-m", "pip", "install", "-r", str(req)], cwd=app_root)
    log = app_root / "logs" / "pip.log"
    log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    return {"mode": "live", "requirements": str(req), "log": str(log)}


def _module_importable(py: Path, module: str) -> bool:
    try:
        result = subprocess.run(
            [str(py), "-c", f"import {module}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_runtime_deps(app: PythonApp, app_root: Path, py: Path) -> None:
    """Installe gunicorn/uvicorn/Django manquants avant Start (cause fréquente d'échec)."""
    if provision_mode() == "mock" or not py.exists():
        return
    missing: list[str] = []
    if app.mode == PythonApp.Mode.ASGI:
        if not _module_importable(py, "uvicorn"):
            missing.append("uvicorn[standard]")
    else:
        if not _module_importable(py, "gunicorn"):
            missing.append("gunicorn")
    if app.framework == PythonApp.Framework.DJANGO and not _module_importable(py, "django"):
        missing.append("Django")
    if not missing:
        return
    log = app_root / "logs" / "pip.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = _run([str(py), "-m", "pip", "install", *missing], cwd=app_root)
        log.write_text(
            f"# auto-install avant Start: {' '.join(missing)}\n{result.stdout}\n{result.stderr}\n",
            encoding="utf-8",
        )
    except VZoneAPIException as exc:
        stderr = (exc.extra or {}).get("stderr") or str(exc)
        raise VZoneAPIException(
            detail=f"Dépendances manquantes ({', '.join(missing)}) et installation échouée. "
            f"Lancez « pip install » puis réessayez. {str(stderr)[:180]}",
            code="deps_install_failed",
            status_code=502,
            extra=exc.extra,
        ) from exc


def _tail_log(path: Path, lines: int = 40) -> str:
    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
    except OSError:
        return ""


def _process_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    if port <= 0:
        return False
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_port(port: int, *, timeout_s: float = 15.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _port_listening(port):
            return True
        time.sleep(0.25)
    return False


def _kill_app_pid(pid: int | None) -> None:
    if not pid:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError, OSError):
                return
        time.sleep(0.35)
        if not _process_alive(pid):
            return


def normalize_app_domain(value: str) -> str:
    """Normalise Application URL (sans schéma / chemin / www)."""
    v = (value or "").strip().lower()
    for prefix in ("https://", "http://"):
        if v.startswith(prefix):
            v = v[len(prefix) :]
    v = v.split("/")[0].split("?")[0].strip(".")
    if v.startswith("www."):
        v = v[4:]
    return v

    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
    except OSError:
        return ""


# Variables d'environnement du panel qui ne doivent PAS fuiter vers les apps clients.
_PANEL_ENV_BLOCKLIST = (
    "DJANGO_SETTINGS_MODULE",
    "DJANGO_CONFIGURATION",
    "VZONE_ROOT",
    "VZONE_DATA_ROOT",
    "DATABASE_URL",
    "CELERY_BROKER_URL",
    "REDIS_URL",
)


def _child_process_env(app: PythonApp, app_root: Path, venv_dir: Path) -> dict[str, str]:
    """
    Environnement isolé pour gunicorn/uvicorn.
    Sans ça, DJANGO_SETTINGS_MODULE=vzone.settings.production du service
    vzone-api est hérité et casse le démarrage des apps Django clients.
    """
    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    for key in _PANEL_ENV_BLOCKLIST:
        env.pop(key, None)
    # Retirer aussi toute clé DJANGO_* héritée du panel
    for key in list(env):
        if key.startswith("DJANGO_"):
            env.pop(key, None)

    env["VIRTUAL_ENV"] = str(venv_dir)
    env["PATH"] = f"{venv_dir / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    # PYTHONPATH = uniquement le root de l'app (pas le PYTHONPATH du panel)
    env["PYTHONPATH"] = str(app_root)
    env["HOME"] = str(user_home(app.owner))

    if app.framework == PythonApp.Framework.DJANGO:
        pkg = detect_django_project_package(app_root)
        env["DJANGO_SETTINGS_MODULE"] = f"{pkg}.settings"

    for key, value in (app.env_vars or {}).items():
        env[str(key)] = str(value)
    return env


def _build_start_command(app: PythonApp, app_root: Path, py: Path) -> list[str]:
    (app_root / "logs").mkdir(parents=True, exist_ok=True)
    if app.mode == PythonApp.Mode.ASGI:
        target = app.entrypoint if ":" in app.entrypoint else "asgi:application"
        return [
            str(py),
            "-m",
            "uvicorn",
            target,
            "--host",
            "127.0.0.1",
            "--port",
            str(app.port),
            "--app-dir",
            str(app_root),
        ]
    # WSGI via gunicorn (sans --daemon : PID fiable + détection d'échec immédiate)
    wsgi_target = (
        app.entrypoint.replace(".py", ":application")
        if app.entrypoint.endswith(".py")
        else app.entrypoint
    )
    return [
        str(py),
        "-m",
        "gunicorn",
        wsgi_target,
        "--bind",
        f"127.0.0.1:{app.port}",
        "--chdir",
        str(app_root),
        "--workers",
        "1",
        "--access-logfile",
        str(app_root / "logs" / "access.log"),
        "--error-logfile",
        str(app_root / "logs" / "error.log"),
        "--capture-output",
    ]


@transaction.atomic
def start_python_app(app: PythonApp) -> PythonApp:
    if not app.is_active:
        raise VZoneAPIException(detail="Application désactivée.", code="inactive", status_code=400)
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    venv_dir = Path(app.venv_path) if app.venv_path else cpanel_venv_path(app.owner, app.name, app.python_version)
    py = venv_python(venv_dir)
    pid_file = app_root / "logs" / "app.pid"
    error_log = app_root / "logs" / "error.log"
    (app_root / "logs").mkdir(parents=True, exist_ok=True)

    env = _child_process_env(app, app_root, venv_dir)

    if provision_mode() == "mock" or not py.exists():
        if not py.exists() and provision_mode() != "mock":
            raise VZoneAPIException(
                detail=f"Virtualenv introuvable : {venv_dir}. Recréez l'application ou le venv.",
                code="venv_missing",
                status_code=400,
                extra={"venv": str(venv_dir)},
            )
        fake_pid = 10000 + (app.pk or 1)
        pid_file.write_text(str(fake_pid), encoding="utf-8")
        app.pid = fake_pid
        app.status = PythonApp.Status.RUNNING
        app.last_error = ""
        app.last_started_at = timezone.now()
        app.save()
        write_app_config(app)
        _refresh_domain_routing(app.domain_name)
        return app

    # Arrêter une instance précédente sur le même pid
    if app.pid or pid_file.exists():
        try:
            stop_python_app(app)
            app.refresh_from_db()
        except Exception:  # noqa: BLE001
            logger.debug("stop avant start ignoré", exc_info=True)

    ensure_runtime_deps(app, app_root, py)

    if app.mode == PythonApp.Mode.WSGI and not (app_root / "passenger_wsgi.py").exists():
        raise VZoneAPIException(
            detail=f"passenger_wsgi.py introuvable dans {app_root}. "
            "L'Application root doit contenir passenger_wsgi.py (comme cPanel).",
            code="no_passenger_wsgi",
            status_code=400,
            extra={"root": str(app_root)},
        )

    cmd = _build_start_command(app, app_root, py)
    try:
        access_f = open(app_root / "logs" / "access.log", "a", encoding="utf-8")
        error_f = open(error_log, "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=str(app_root),
            env=env,
            stdout=access_f,
            stderr=error_f,
            start_new_session=True,
        )
        # Attendre que le port écoute (gunicorn peut mettre >1s à binder)
        if not _wait_port(app.port, timeout_s=20.0):
            if proc.poll() is not None:
                tail = _tail_log(error_log)
                raise RuntimeError(
                    f"Le process s'est arrêté (code {proc.returncode}).\n"
                    f"{tail[-2000:] if tail else 'Voir logs/error.log — pip install gunicorn Django ?'}"
                )
            _kill_app_pid(proc.pid)
            tail = _tail_log(error_log)
            raise RuntimeError(
                f"Le port {app.port} n'écoute pas après démarrage.\n"
                f"{tail[-2000:] if tail else 'Voir logs/error.log'}"
            )
        if proc.poll() is not None:
            tail = _tail_log(error_log)
            raise RuntimeError(
                f"Le process s'est arrêté (code {proc.returncode}).\n"
                f"{tail[-2000:] if tail else 'Voir logs/error.log — pip install gunicorn Django ?'}"
            )
        pid_file.write_text(str(proc.pid), encoding="utf-8")
        app.pid = proc.pid
        app.status = PythonApp.Status.RUNNING
        app.last_error = ""
        app.last_started_at = timezone.now()
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        if isinstance(exc, VZoneAPIException):
            detail = str(exc.detail)
            extra = dict(exc.extra or {})
        else:
            extra = {"error": detail, "stderr": _tail_log(error_log)}
        if hasattr(exc, "extra") and isinstance(getattr(exc, "extra"), dict):
            extra.update(exc.extra)
        app.status = PythonApp.Status.ERROR
        app.last_error = detail[:2000]
        app.pid = None
        if pid_file.exists():
            pid_file.unlink(missing_ok=True)
        app.save()
        write_app_config(app)
        raise VZoneAPIException(
            detail=f"Impossible de démarrer l'application : {detail[:300]}",
            code="start_failed",
            status_code=400,
            extra=extra,
        ) from exc
    app.save()
    write_app_config(app)
    _refresh_domain_routing(app.domain_name)
    return app


@transaction.atomic
def stop_python_app(app: PythonApp) -> PythonApp:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    pid_file = app_root / "logs" / "app.pid"
    pid = app.pid
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = app.pid

    if provision_mode() != "mock" and pid and should_execute():
        _kill_app_pid(pid)

    if pid_file.exists():
        pid_file.unlink(missing_ok=True)
    app.pid = None
    app.status = PythonApp.Status.STOPPED
    app.last_error = ""
    app.save()
    write_app_config(app)
    _refresh_domain_routing(app.domain_name)
    return app


@transaction.atomic
def restart_python_app(app: PythonApp) -> PythonApp:
    stop_python_app(app)
    return start_python_app(app)


@transaction.atomic
def delete_python_app(app: PythonApp, *, remove_files: bool = False) -> None:
    if app.status == PythonApp.Status.RUNNING:
        stop_python_app(app)
    cfg = config_root() / str(app.owner_id) / f"{app.name}.json"
    if cfg.exists():
        cfg.unlink(missing_ok=True)
    if remove_files:
        try:
            _, app_root = resolve_app_root(app.owner, app.relative_root)
            shutil.rmtree(app_root, ignore_errors=True)
        except VZoneAPIException:
            pass
        venv = Path(app.venv_path) if app.venv_path else cpanel_venv_path(app.owner, app.name, app.python_version)
        shutil.rmtree(venv, ignore_errors=True)
        try:
            parent = venv.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass
    domain = app.domain_name
    app.delete()
    _refresh_domain_routing(domain)


def reconcile_python_apps() -> dict:
    """
    Relance les apps marquées RUNNING dont le process/port est mort
    (ex. après restart vzone-api avant KillMode=process).
    """
    if provision_mode() == "mock":
        return {"mode": "mock", "checked": 0, "restarted": [], "failed": []}

    checked = 0
    restarted: list[str] = []
    failed: list[dict] = []
    qs = PythonApp.objects.filter(is_active=True, status=PythonApp.Status.RUNNING, port__gt=0)
    for app in qs.iterator():
        checked += 1
        if _port_listening(app.port) and _process_alive(app.pid):
            continue
        logger.warning(
            "Python app %s (port %s) RUNNING mais inactive — relance",
            app.name,
            app.port,
        )
        try:
            start_python_app(app)
            restarted.append(app.name)
        except Exception as exc:  # noqa: BLE001
            failed.append({"name": app.name, "error": str(exc)[:300]})
            logger.exception("reconcile start failed for %s", app.name)

    # Toujours resync vhosts pour les apps RUNNING liées à un domaine
    try:
        from apps.domains.services import refresh_web_routing

        refresh_web_routing()
    except Exception:  # noqa: BLE001
        logger.debug("reconcile vhost sync skip", exc_info=True)

    return {
        "mode": "live",
        "checked": checked,
        "restarted": restarted,
        "failed": failed,
    }


def read_logs(app: PythonApp, *, lines: int = 100) -> dict:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    result = {}
    for name in ("error.log", "access.log", "pip.log"):
        path = app_root / "logs" / name
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
            result[name] = "\n".join(content[-lines:])
        else:
            result[name] = ""
    return result


def overview_for(user: User) -> dict:
    qs = apps_qs(user)
    return {
        "apps": qs.count(),
        "running": qs.filter(status=PythonApp.Status.RUNNING).count(),
        "stopped": qs.filter(status=PythonApp.Status.STOPPED).count(),
        "error": qs.filter(status=PythonApp.Status.ERROR).count(),
        "provision_mode": provision_mode(),
        "home_path": str(user_home(user)),
    }
