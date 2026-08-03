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

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")

WSGI_TEMPLATE = '''\
"""Entrée WSGI générée par V-zone Panel."""
import os
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

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
    app_root.mkdir(parents=True, exist_ok=True)
    (app_root / "logs").mkdir(exist_ok=True)
    req = app_root / "requirements.txt"
    if not req.exists():
        req.write_text(REQUIREMENTS_TEMPLATE, encoding="utf-8")
    if mode == PythonApp.Mode.ASGI:
        entry = app_root / "asgi.py"
        if not entry.exists():
            entry.write_text(ASGI_TEMPLATE, encoding="utf-8")
    else:
        entry = app_root / "passenger_wsgi.py"
        if not entry.exists():
            entry.write_text(WSGI_TEMPLATE, encoding="utf-8")
    readme = app_root / "README.vzone.md"
    if not readme.exists():
        readme.write_text(
            f"# Application Python V-zone\n\nMode: {mode}\nFramework: {framework}\n",
            encoding="utf-8",
        )


def create_venv(app_root: Path, version: str) -> Path:
    venv_dir = app_root / ".venv"
    if provision_mode() == "mock" or not should_execute():
        venv_dir.mkdir(parents=True, exist_ok=True)
        (venv_dir / "bin").mkdir(exist_ok=True)
        marker = venv_dir / "pyvenv.cfg"
        marker.write_text(f"home = mock\nversion = {version}\n", encoding="utf-8")
        return venv_dir
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

    rel = relative_root.strip() or f"apps/{slug}"
    rel, app_root = resolve_app_root(owner, rel)
    _scaffold(app_root, mode, framework)
    venv_dir = create_venv(app_root, python_version)

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
        domain_name=domain_name.strip().lower(),
        notes=notes,
        status=PythonApp.Status.STOPPED,
    )
    write_app_config(app)
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
    if label is not None:
        app.label = label
    if entrypoint is not None:
        app.entrypoint = entrypoint
    if domain_name is not None:
        app.domain_name = domain_name.strip().lower()
    if env_vars is not None:
        app.env_vars = env_vars
    if notes is not None:
        app.notes = notes
    if is_active is not None:
        app.is_active = is_active
    app.save()
    write_app_config(app)
    return app


def install_requirements(app: PythonApp) -> dict:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    req = app_root / (app.requirements_file or "requirements.txt")
    if not req.exists():
        raise VZoneAPIException(detail="requirements.txt introuvable.", code="no_requirements", status_code=400)
    venv_dir = Path(app.venv_path) if app.venv_path else app_root / ".venv"
    py = venv_python(venv_dir)
    if provision_mode() == "mock" or not py.exists():
        log = app_root / "logs" / "pip.log"
        log.write_text(f"mock install -r {req.name}\n", encoding="utf-8")
        return {"mode": "mock", "requirements": str(req), "log": str(log)}
    result = _run([str(py), "-m", "pip", "install", "-r", str(req)], cwd=app_root)
    log = app_root / "logs" / "pip.log"
    log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    return {"mode": "live", "requirements": str(req), "log": str(log)}


def _build_start_command(app: PythonApp, app_root: Path, py: Path) -> list[str]:
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
    # WSGI via gunicorn if available in venv, else python -m http fallback for scaffold
    return [
        str(py),
        "-m",
        "gunicorn",
        app.entrypoint.replace(".py", ":application") if app.entrypoint.endswith(".py") else app.entrypoint,
        "--bind",
        f"127.0.0.1:{app.port}",
        "--chdir",
        str(app_root),
        "--pid",
        str(app_root / "logs" / "app.pid"),
        "--access-logfile",
        str(app_root / "logs" / "access.log"),
        "--error-logfile",
        str(app_root / "logs" / "error.log"),
        "--daemon",
    ]


@transaction.atomic
def start_python_app(app: PythonApp) -> PythonApp:
    if not app.is_active:
        raise VZoneAPIException(detail="Application désactivée.", code="inactive", status_code=400)
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    venv_dir = Path(app.venv_path) if app.venv_path else app_root / ".venv"
    py = venv_python(venv_dir)
    pid_file = app_root / "logs" / "app.pid"
    env = os.environ.copy()
    for key, value in (app.env_vars or {}).items():
        env[str(key)] = str(value)

    if provision_mode() == "mock" or not py.exists():
        fake_pid = 10000 + (app.pk or 1)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(fake_pid), encoding="utf-8")
        app.pid = fake_pid
        app.status = PythonApp.Status.RUNNING
        app.last_error = ""
        app.last_started_at = timezone.now()
        app.save()
        write_app_config(app)
        return app

    cmd = _build_start_command(app, app_root, py)
    try:
        if app.mode == PythonApp.Mode.ASGI:
            proc = subprocess.Popen(
                cmd,
                cwd=str(app_root),
                env=env,
                stdout=open(app_root / "logs" / "access.log", "a", encoding="utf-8"),
                stderr=open(app_root / "logs" / "error.log", "a", encoding="utf-8"),
                start_new_session=True,
            )
            pid_file.write_text(str(proc.pid), encoding="utf-8")
            app.pid = proc.pid
        else:
            _run(cmd, cwd=app_root, env=env)
            if pid_file.exists():
                app.pid = int(pid_file.read_text(encoding="utf-8").strip() or "0") or None
        app.status = PythonApp.Status.RUNNING
        app.last_error = ""
        app.last_started_at = timezone.now()
    except Exception as exc:  # noqa: BLE001
        app.status = PythonApp.Status.ERROR
        app.last_error = str(exc)
        app.pid = None
        app.save()
        write_app_config(app)
        raise VZoneAPIException(
            detail="Impossible de démarrer l'application.",
            code="start_failed",
            status_code=502,
            extra={"error": str(exc)},
        ) from exc
    app.save()
    write_app_config(app)
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
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            logger.info("Processus Python %s déjà arrêté", pid)

    if pid_file.exists():
        pid_file.unlink(missing_ok=True)
    app.pid = None
    app.status = PythonApp.Status.STOPPED
    app.last_error = ""
    app.save()
    write_app_config(app)
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
    app.delete()


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
    }
