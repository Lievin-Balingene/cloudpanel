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
from apps.security.runas import build_runas_cmd

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
    # Propriétaire = compte jail dès la création (évite SQLite/logs readonly plus tard)
    fix_client_paths(owner, app_root, venv_dir, venv_dir.parent)

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
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f"mock install -r {req.name}\n", encoding="utf-8")
        return {"mode": "mock", "requirements": str(req), "log": str(log)}
    # Ownership avant pip jailé
    fix_client_paths(app.owner, app_root, venv_dir)
    result = _run_as_owner(
        app.owner,
        [str(py), "-m", "pip", "install", "-r", str(req)],
        cwd=app_root,
    )
    log = app_root / "logs" / "pip.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    except OSError:
        pass
    fix_client_paths(app.owner, app_root, venv_dir)
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
    fix_client_paths(app.owner, app_root, Path(app.venv_path) if app.venv_path else app_root)
    try:
        result = _run_as_owner(app.owner, [str(py), "-m", "pip", "install", *missing], cwd=app_root)
        try:
            log.write_text(
                f"# auto-install avant Start: {' '.join(missing)}\n{result.stdout}\n{result.stderr}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        fix_client_paths(app.owner, app_root)
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


_LOG_NOISE_RE = re.compile(
    r"(?i)("
    r"xmlrpc\.php|wlwmanifest\.xml|wp-includes|wp-admin|wp-content|"
    r"/wordpress|/wp/|phpmyadmin|favicon\.ico|robots\.txt|"
    r"Not Found:\s*/+/|"
    r"\.env(\.bak)?|actuator/health|cgi-bin|"
    r"union\s+select|eval\(|base64_decode"
    r")"
)

_EXIT_HINTS = {
    127: (
        "Code 127 : commande introuvable. "
        "Le binaire Python du venv ou le module manquent — "
        "installez les dépendances (pip install gunicorn) puis réessayez."
    ),
    126: "Code 126 : permission refusée pour exécuter le binaire Python/venv.",
    1: "Code 1 : échec au démarrage (module manquant ou erreur d'import).",
}


def _filter_log_noise(text: str) -> str:
    """Retire le bruit scanners (WordPress probes, etc.) des extraits de logs."""
    if not text:
        return ""
    kept: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if _LOG_NOISE_RE.search(s):
            continue
        # Lignes 404 HTTP génériques sans stack Python
        if re.match(r"(?i)^(not found|404|forbidden|403)\b", s) and "traceback" not in s.lower():
            continue
        kept.append(line)
    return "\n".join(kept[-40:])


def _log_bytes_since(path: Path, offset: int) -> str:
    if not path.exists():
        return ""
    try:
        size = path.stat().st_size
        if offset < 0 or offset > size:
            offset = 0
        with path.open("rb") as fh:
            fh.seek(offset)
            raw = fh.read()
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _clip_end(text: str, limit: int) -> str:
    """Tronque en gardant la FIN (là où est l'exception Python)."""
    t = (text or "").strip()
    if limit <= 0 or len(t) <= limit:
        return t
    return "…" + t[-(limit - 1) :]


def _summarize_traceback(text: str) -> str:
    """Extrait les lignes d'exception utiles (fin de traceback), pas le milieu gunicorn."""
    clean = _filter_log_noise(text).strip()
    if not clean:
        return ""
    lines = [ln.rstrip() for ln in clean.splitlines() if ln.strip()]
    interesting: list[str] = []
    for ln in lines:
        s = ln.strip()
        if re.search(
            r"(ModuleNotFoundError|ImportError|ImproperlyConfigured|PermissionError|"
            r"FileNotFoundError|OSError|RuntimeError|ValueError|KeyError|"
            r"HaltServer|Worker failed to boot|Address already in use|"
            r"django\.core\.exceptions|"
            r"\w+(Error|Exception)\s*:)",
            s,
        ):
            interesting.append(s)
        elif s.startswith("Reason:"):
            interesting.append(s)
    if interesting:
        return "\n".join(list(dict.fromkeys(interesting))[-5:])
    return "\n".join(lines[-15:])


def _venv_version_mismatch_hint(venv_dir: Path, labeled_version: str) -> str:
    """Ex. dossier …/3.12/ mais lib/python3.10 → binaire/fallback incohérent."""
    lib = venv_dir / "lib"
    if not lib.is_dir():
        return ""
    py_dirs = sorted(p.name for p in lib.iterdir() if p.is_dir() and p.name.startswith("python"))
    if not py_dirs:
        return ""
    label = (labeled_version or "").strip()
    if not label:
        return ""
    if any(label in name for name in py_dirs):
        return ""
    actual = py_dirs[0]
    return (
        f" Venv incohérent : dossier « {label} » mais {actual} "
        f"(recréez le virtualenv avec python{label} installé)."
    )


def _ensure_venv_matches_labeled_version(
    owner: User,
    venv_dir: Path,
    labeled_version: str,
) -> Path:
    """
    Si le venv (ex. …/3.12/) contient lib/python3.10, on le recrée.
    Sinon gunicorn tourne avec un mauvais interpréteur / deps.
    """
    hint = _venv_version_mismatch_hint(venv_dir, labeled_version)
    if not hint:
        return venv_python(venv_dir)

    logger.warning("venv mismatch %s — tentative de recreation", hint.strip())
    version = (labeled_version or "3.12").strip() or "3.12"
    if provision_mode() == "mock":
        return venv_python(venv_dir)

    if not should_execute():
        raise VZoneAPIException(
            detail=hint.strip(),
            code="venv_version_mismatch",
            status_code=400,
            extra={"venv": str(venv_dir), "expected": version},
        )

    # pythonX.Y doit exister sur le serveur
    py_bin = python_binary(version)
    try:
        probe = subprocess.run(
            [py_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        ver_out = (probe.stdout or probe.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VZoneAPIException(
            detail=(
                f"Python {version} introuvable sur le serveur ({exc}). "
                f"Installez python{version} ou changez la version de l'app."
            ),
            code="python_version_missing",
            status_code=400,
            extra={"python_version": version, "binary": py_bin},
        ) from exc
    if probe.returncode != 0 or (version not in ver_out and f"Python {version}" not in ver_out):
        # Tolère « Python 3.12.x »
        if version not in ver_out:
            raise VZoneAPIException(
                detail=(
                    f"Le binaire `{py_bin}` ne fournit pas Python {version} ({ver_out or 'échec'}). "
                    f"Installez python{version}-venv ou sélectionnez une autre version d'app."
                ),
                code="python_version_missing",
                status_code=400,
                extra={"python_version": version, "binary": py_bin, "version_out": ver_out},
            )

    shutil.rmtree(venv_dir, ignore_errors=True)
    create_venv(venv_dir, version)
    fix_client_paths(owner, venv_dir, venv_dir.parent)
    still = _venv_version_mismatch_hint(venv_dir, version)
    if still:
        raise VZoneAPIException(
            detail=still.strip(),
            code="venv_version_mismatch",
            status_code=400,
            extra={"venv": str(venv_dir), "expected": version},
        )
    return venv_python(venv_dir)


def _reclaim_app_logs_for_panel(owner: User, logs: Path, *files: Path) -> None:
    """Après chown jail, le panel doit pouvoir append access/error.log."""
    import shlex

    for path in files:
        try:
            if path.exists():
                path.chmod(0o666)
        except OSError:
            pass
    try:
        if logs.exists():
            logs.chmod(0o775)
    except OSError:
        pass

    fix_client_paths(owner, logs, *files)

    try:
        from apps.accounts.linux_users import jail_username_for
        from apps.security.runas import build_runas_cmd, runas_available

        if not (runas_available() and provision_mode() != "mock"):
            return
        jail = jail_username_for(owner)
        file_list = " ".join(shlex.quote(str(p)) for p in files if p)
        script = (
            f"mkdir -p {shlex.quote(str(logs))} && chmod 775 {shlex.quote(str(logs))} 2>/dev/null || true; "
            f"for f in {file_list}; do "
            f"  rm -f \"$f\" 2>/dev/null || true; "
            f"  touch \"$f\" 2>/dev/null || true; "
            f"  chmod 666 \"$f\" 2>/dev/null || true; "
            f"done"
        )
        subprocess.run(
            build_runas_cmd(jail, ["bash", "-c", script]),
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        fix_client_paths(owner, logs, *files)
        for path in files:
            try:
                if path.exists():
                    path.chmod(0o666)
            except OSError:
                pass
            try:
                subprocess.run(
                    ["setfacl", "-m", f"u:vzone:rw", str(path)],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
                pass
    except Exception:  # noqa: BLE001
        logger.debug("reclaim app logs skip", exc_info=True)


def _open_app_log_append(owner: User, path: Path):
    """Ouvre un log en append ; récupère PermissionError post-chown jail."""
    try:
        return open(path, "a", encoding="utf-8")
    except OSError as first:
        logger.warning("open log %s: %s — reclaim", path, first)
        _reclaim_app_logs_for_panel(owner, path.parent, path)
        try:
            return open(path, "a", encoding="utf-8")
        except OSError as second:
            raise VZoneAPIException(
                detail=(
                    f"Permission denied sur `{path.name}` ({second}). "
                    "Les logs sont owned par le compte jail : "
                    f"sudo {FIX_APP_PERMS} {_jail_name(owner)} {path.parent}"
                ),
                code="log_permission",
                status_code=500,
                extra={"path": str(path)},
            ) from second


def _format_start_failure(*, returncode: int | None, stderr_new: str, port: int = 0) -> str:
    """Message d'échec clair, sans pollution scanners WordPress."""
    clean = _filter_log_noise(stderr_new).strip()
    low = clean.lower()
    # Bug historique : env … -- cmd → env traite "--" comme binaire (code 127)
    if "env:" in low and ("'--'" in clean or '"--"' in clean or "‘--’" in clean):
        return (
            "Échec lancement (env/--) : corrigez le panel (vzone-runas / build_runas_cmd) "
            "ou mettez à jour (≥ 0.35.7). Détail : "
            + (clean[-400:] if clean else "env: '--': No such file or directory")
        )
    summary = _summarize_traceback(clean)
    if "permission denied" in (summary or clean).lower() and (
        "error.log" in (summary or clean).lower() or "access.log" in (summary or clean).lower()
    ):
        summary = (
            (summary + "\n" if summary else "")
            + "Logs non inscriptibles (jail vs panel). Mettez à jour (≥ 0.35.28) "
            "ou : sudo vzone-fix-app-perms <user> ~/…/logs && chmod 666 ~/…/logs/*.log"
        )
    parts: list[str] = []
    if returncode is not None:
        if returncode == 127 and "env:" in low:
            parts.append("Code 127 : commande introuvable lors du spawn (souvent env/runas).")
        else:
            parts.append(_EXIT_HINTS.get(returncode, f"Le process s'est arrêté (code {returncode})."))
    elif port:
        parts.append(f"Le port {port} n'écoute pas après démarrage.")
    if summary:
        parts.append(summary)
    elif returncode == 127:
        parts.append("Astuce : dans le venv de l'app → pip install gunicorn (WSGI) ou uvicorn (ASGI).")
    else:
        parts.append(
            "Aucun détail utile dans error.log (bruit filtré). "
            "Vérifiez logs/error.log et les dépendances du venv."
        )
    return "\n".join(parts)


def _entrypoint_import_module(app: PythonApp) -> str:
    ep = (app.entrypoint or "").strip() or (
        "asgi:application" if app.mode == PythonApp.Mode.ASGI else "passenger_wsgi.py"
    )
    if ep.endswith(".py"):
        return ep[:-3].replace("\\", "/").replace("/", ".")
    if ":" in ep:
        return ep.split(":", 1)[0].replace("\\", "/").replace("/", ".")
    return ep.replace("\\", "/").replace("/", ".")


def _preflight_app_import(
    app: PythonApp,
    app_root: Path,
    py: Path,
    env: dict[str, str],
    *,
    venv_dir: Path | None = None,
) -> None:
    """Importe le module WSGI/ASGI avant gunicorn pour remonter l'erreur réelle."""
    mod = _entrypoint_import_module(app)
    if not mod or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", mod):
        return
    probe_py = (
        "import sys, importlib;"
        f"sys.path.insert(0, {str(app_root)!r});"
        f"importlib.import_module({mod!r})"
    )
    try:
        from apps.accounts.linux_users import jail_username_for
        from apps.security.runas import build_runas_cmd, runas_available

        probe = [str(py), "-c", probe_py]
        if runas_available():
            jail = jail_username_for(app.owner)
            probe = build_runas_cmd(jail, probe, env=env)
        proc = subprocess.run(
            probe,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=str(app_root),
        )
    except VZoneAPIException:
        raise
    except Exception:  # noqa: BLE001
        return
    if proc.returncode == 0:
        return
    err = _summarize_traceback((proc.stderr or proc.stdout or "").strip())
    if _is_runas_infra_error(err):
        raise VZoneAPIException(
            detail=f"Préflight import impossible (runas) : {_clip_end(err, 280)}",
            code="runas_broken",
            status_code=500,
            extra={"stderr": err},
        )
    hint = _venv_version_mismatch_hint(venv_dir or Path(), app.python_version)
    raise VZoneAPIException(
        detail=(
            f"Échec import `{mod}` (avant gunicorn). "
            + (_clip_end(err, 500) if err else "Erreur d'import inconnue.")
            + hint
        ),
        code="app_import_failed",
        status_code=400,
        extra={"module": mod, "stderr": err[-1500:] if err else ""},
    )


def _is_runas_infra_error(err: str) -> bool:
    """True si l'échec vient de vzone-runas / runuser, pas d'un import Python."""
    low = (err or "").lower()
    markers = (
        "runuser",
        "vzone-runas",
        "exec: runuser",
        "ni runuser ni su",
        "root requis",
        "hors groupe",
        "compte os absent",
        "username invalide",
        "username réservé",
        "home hors",
        "env: '--'",
        'env: "--"',
        "env: ‘--’",
    )
    return any(m in low for m in markers)


def _preflight_runtime_module(app: PythonApp, py: Path) -> None:
    """Vérifie que gunicorn/uvicorn est importable avant Popen (évite code 127 opaque)."""
    mod = "uvicorn" if app.mode == PythonApp.Mode.ASGI else "gunicorn"
    if not py.is_file():
        raise VZoneAPIException(
            detail=f"Interpréteur introuvable : {py}",
            code="python_missing",
            status_code=400,
        )
    try:
        from apps.accounts.linux_users import jail_username_for
        from apps.security.runas import build_runas_cmd, runas_available

        probe = [str(py), "-c", f"import {mod}"]
        if runas_available():
            jail = jail_username_for(app.owner)
            probe = build_runas_cmd(jail, probe)
        proc = subprocess.run(
            probe,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except VZoneAPIException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise VZoneAPIException(
            detail=f"Impossible de vérifier {mod} : {exc}",
            code="preflight_failed",
            status_code=400,
        ) from exc
    if proc.returncode != 0:
        err = _filter_log_noise((proc.stderr or proc.stdout or "").strip())[:400]
        if _is_runas_infra_error(err):
            raise VZoneAPIException(
                detail=(
                    "Impossible d'exécuter sous le compte client (vzone-runas / runuser). "
                    "Mettez à jour le panel (update.sh réinstalle vzone-runas) "
                    "ou installez util-linux. "
                    f"Détail : {err[:220]}"
                ),
                code="runas_broken",
                status_code=500,
                extra={"module": mod, "returncode": proc.returncode, "stderr": err},
            )
        raise VZoneAPIException(
            detail=(
                f"Module `{mod}` absent du virtualenv. "
                f"Lancez « Installer les dépendances » ou : "
                f"{py} -m pip install {mod}"
                + (f" — {err}" if err else "")
            ),
            code="runtime_module_missing",
            status_code=400,
            extra={"module": mod, "returncode": proc.returncode},
        )


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


def _read_app_pid_file(pid_file: Path, fallback: int | None) -> int | None:
    """Lit logs/app.pid sans faire planter le stop/start (perms jail)."""
    try:
        if not pid_file.exists():
            return fallback
        return int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return fallback
    except OSError as exc:
        logger.warning("lecture pid %s: %s", pid_file, exc)
        return fallback


def _clear_app_pid_file(owner: User, pid_file: Path) -> None:
    """
    Supprime logs/app.pid même si owned par le compte jail.

    Après fix-app-perms / chown jail, le panel (user vzone) peut ne plus
    pouvoir unlink → PermissionError → HTTP 500. On répare puis on retente ;
    le stop DB doit quand même aboutir.
    """
    try:
        if not pid_file.exists():
            return
    except OSError:
        return

    def _try_unlink() -> bool:
        try:
            pid_file.unlink(missing_ok=True)
            return True
        except OSError as exc:
            logger.warning("unlink pid %s: %s", pid_file, exc)
            return False

    if _try_unlink():
        return

    try:
        fix_client_paths(owner, pid_file.parent, pid_file)
    except Exception:  # noqa: BLE001
        logger.debug("fix-app-perms avant unlink pid échoué", exc_info=True)

    if _try_unlink():
        return

    try:
        from apps.accounts.linux_users import jail_username_for
        from apps.security.runas import runas_available
        import shlex

        if runas_available() and provision_mode() != "mock":
            jail = jail_username_for(owner)
            cmd = build_runas_cmd(
                jail,
                ["bash", "-c", f"rm -f -- {shlex.quote(str(pid_file))}"],
            )
            subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except Exception:  # noqa: BLE001
        logger.warning("runas rm pid %s échoué", pid_file, exc_info=True)

    # Dernier essai ; si ça échoue encore on laisse le fichier — statut DB = stopped
    _try_unlink()


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
        # « - » = stdout/stderr hérités (FD ouverts par le panel).
        # Évite PermissionError si error.log est owned par vzone et non par le jail.
        "--access-logfile",
        "-",
        "--error-logfile",
        "-",
        "--capture-output",
    ]


def _grant_jail_write(path: Path, username: str, *, is_dir: bool = False) -> None:
    """Donne l'écriture au compte jail (ACL si possible, sinon chmod permissif)."""
    if not path.exists():
        return
    try:
        spec = f"u:{username}:rwx" if is_dir else f"u:{username}:rw"
        subprocess.run(
            ["setfacl", "-m", spec, str(path)],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    try:
        mode = path.stat().st_mode
        if is_dir:
            path.chmod(mode | 0o775)
        else:
            # SQLite / fichiers données : lecture-écriture pour owner+group+other
            # (owner est souvent « vzone » après deploy panel, process = jail)
            path.chmod(0o666)
    except OSError:
        pass


def _iter_sqlite_files(app_root: Path) -> list[Path]:
    """db.sqlite3 et cousins à la racine + 1 niveau (évite scan massif)."""
    found: list[Path] = []
    patterns = ("*.sqlite3", "*.sqlite", "*.db")
    for pat in patterns:
        found.extend(app_root.glob(pat))
    for sub in ("data", "var", "db", "database", "databases"):
        d = app_root / sub
        if d.is_dir():
            for pat in patterns:
                found.extend(d.glob(pat))
    # Déduplique
    out: list[Path] = []
    seen: set[str] = set()
    for p in found:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


FIX_APP_PERMS = Path("/usr/local/sbin/vzone-fix-app-perms")


def _jail_name(owner: User) -> str:
    try:
        from apps.accounts.linux_users import jail_username_for

        return jail_username_for(owner)
    except Exception:  # noqa: BLE001
        return (owner.username or "").strip().lower()


def fix_client_paths(
    owner: User,
    *paths: Path,
    required: bool = False,
    verify_sqlite_in: Path | None = None,
) -> None:
    """
    Réattribue les chemins au compte jail (via sudo vzone-fix-app-perms).

    À appeler après toute écriture panel (scaffold, pip, logs) pour éviter
    « attempt to write a readonly database » / PermissionError sous gunicorn runas.
    """
    if provision_mode() == "mock":
        return
    jail = _jail_name(owner)
    if not jail:
        return

    unique: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        if raw is None:
            continue
        try:
            p = Path(raw)
            if not p.exists():
                continue
            key = str(p.resolve())
        except OSError:
            key = str(raw)
            p = Path(raw)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    if not unique and verify_sqlite_in is None:
        return

    if not FIX_APP_PERMS.is_file():
        msg = (
            "Helper vzone-fix-app-perms absent. "
            "Exécutez: sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh"
        )
        if required:
            raise VZoneAPIException(detail=msg, code="fix_app_perms_missing", status_code=500)
        logger.warning(msg)
    else:
        for path in unique:
            try:
                proc = subprocess.run(
                    ["sudo", "-n", str(FIX_APP_PERMS), jail, str(path)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or "")[:400]
                    logger.warning("fix-app-perms %s %s → %s %s", jail, path, proc.returncode, err)
                    if required:
                        raise VZoneAPIException(
                            detail=(
                                f"Impossible de corriger les permissions de `{path}` "
                                f"pour `{jail}`: {err or proc.returncode}. "
                                f"Manuel: sudo {FIX_APP_PERMS} {jail} {path}"
                            ),
                            code="fix_app_perms_failed",
                            status_code=500,
                            extra={"path": str(path), "jail": jail},
                        )
                else:
                    logger.info("fix-app-perms OK %s → %s", jail, path)
            except VZoneAPIException:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("fix-app-perms exception: %s", exc)
                if required:
                    raise VZoneAPIException(
                        detail=f"fix-app-perms a échoué: {exc}",
                        code="fix_app_perms_failed",
                        status_code=500,
                    ) from exc

    # Complément ACL/chmod (sans root)
    for path in unique:
        _grant_jail_write(path, jail, is_dir=path.is_dir())
        if path.is_dir():
            for db in _iter_sqlite_files(path):
                _grant_jail_write(db, jail, is_dir=False)

    check_root = verify_sqlite_in
    if check_root is None:
        return
    db_main = Path(check_root) / "db.sqlite3"
    if not db_main.exists():
        return
    try:
        from apps.security.runas import build_runas_cmd, runas_available
        import shlex

        if not runas_available():
            return
        probe = build_runas_cmd(
            jail,
            [
                "bash",
                "-c",
                f"test -w {shlex.quote(str(db_main))} && test -w {shlex.quote(str(check_root))}",
            ],
        )
        proc = subprocess.run(probe, capture_output=True, text=True, timeout=30, check=False)
        if proc.returncode != 0:
            raise VZoneAPIException(
                detail=(
                    f"SQLite toujours en lecture seule pour `{jail}` ({db_main}). "
                    f"Exécutez: sudo {FIX_APP_PERMS} {jail} {check_root} "
                    f"puis redémarrez l'application."
                ),
                code="sqlite_readonly",
                status_code=400,
                extra={"path": str(db_main), "jail": jail},
            )
    except VZoneAPIException:
        raise
    except Exception:  # noqa: BLE001
        logger.debug("sqlite writable probe skip", exc_info=True)


def _run_as_owner(
    owner: User,
    cmd: list[str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Exécute une commande sous l'UID client si runas dispo (pip, etc.)."""
    from apps.security.runas import build_runas_cmd, runas_available

    if provision_mode() == "mock" or not runas_available():
        return _run(cmd, cwd=cwd)
    jail = _jail_name(owner)
    full = build_runas_cmd(jail, cmd)
    try:
        return subprocess.run(
            full,
            check=True,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=300,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        stderr = getattr(exc, "stderr", None) or str(exc)
        raise VZoneAPIException(
            detail="Échec commande Python (jail).",
            code="python_cmd_failed",
            status_code=502,
            extra={"stderr": stderr, "cmd": full},
        ) from exc


def _ensure_app_data_writable(owner: User, app_root: Path, *extra: Path) -> None:
    """Garantie ownership jail avant démarrage gunicorn."""
    fix_client_paths(
        owner,
        app_root,
        *extra,
        required=True,
        verify_sqlite_in=app_root,
    )


def _prepare_app_logs(owner: User, app_root: Path) -> tuple[Path, Path]:
    """Crée logs/ accessibles au compte jail (sinon gunicorn → PermissionError)."""
    import shlex

    logs = app_root / "logs"
    access_log = logs / "access.log"
    error_log = logs / "error.log"
    try:
        logs.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("mkdir logs %s: %s", logs, exc)

    # Fichiers créés par le process « vzone » : ouvrir en écriture pour le jail
    for path in (access_log, error_log):
        if not path.exists():
            try:
                path.touch()
            except OSError:
                pass
        try:
            # 666 : panel (vzone) + client (jail) peuvent append ; ACL home peut déjà suffire
            path.chmod(0o666)
        except OSError:
            pass

    try:
        from apps.accounts.linux_users import jail_username_for
        from apps.security.runas import build_runas_cmd, runas_available

        if runas_available() and provision_mode() != "mock":
            jail = jail_username_for(owner)
            # Recrée sous UID client si le fichier est encore owned par vzone
            script = (
                f"mkdir -p {shlex.quote(str(logs))} && "
                f"chmod u+w {shlex.quote(str(logs))} 2>/dev/null || true; "
                # Si non inscriptible : supprimer (dir owned par le client) puis retoucher
                f"for f in {shlex.quote(str(access_log))} {shlex.quote(str(error_log))}; do "
                f"  if ! test -w \"$f\" 2>/dev/null; then rm -f \"$f\"; fi; "
                f"  touch \"$f\" 2>/dev/null || true; "
                f"  chmod 664 \"$f\" 2>/dev/null || true; "
                f"done; "
                f"chmod 775 {shlex.quote(str(logs))} 2>/dev/null || true"
            )
            probe = build_runas_cmd(jail, ["bash", "-c", script])
            subprocess.run(probe, capture_output=True, text=True, timeout=45, check=False)
            _grant_jail_write(logs, jail, is_dir=True)
            _grant_jail_write(access_log, jail, is_dir=False)
            _grant_jail_write(error_log, jail, is_dir=False)
    except Exception:  # noqa: BLE001
        logger.debug("prepare_app_logs runas skip", exc_info=True)

    try:
        logs.chmod(0o775)
    except OSError:
        pass
    # Toujours réaligner le propriétaire après écritures panel
    fix_client_paths(owner, logs, access_log, error_log, app_root)
    # Panel doit pouvoir rouvrir les logs en append (FD pour gunicorn)
    _reclaim_app_logs_for_panel(owner, logs, access_log, error_log)
    return access_log, error_log


@transaction.atomic
def start_python_app(app: PythonApp) -> PythonApp:
    if not app.is_active:
        raise VZoneAPIException(detail="Application désactivée.", code="inactive", status_code=400)
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    venv_dir = Path(app.venv_path) if app.venv_path else cpanel_venv_path(app.owner, app.name, app.python_version)
    py = _ensure_venv_matches_labeled_version(app.owner, venv_dir, app.python_version)
    access_log, error_log = _prepare_app_logs(app.owner, app_root)
    _ensure_app_data_writable(app.owner, app_root, venv_dir)
    pid_file = app_root / "logs" / "app.pid"

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
        try:
            pid_file.write_text(str(fake_pid), encoding="utf-8")
        except OSError:
            _reclaim_app_logs_for_panel(app.owner, pid_file.parent, pid_file)
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
    _preflight_runtime_module(app, py)
    _preflight_app_import(app, app_root, py, env, venv_dir=venv_dir)

    if app.mode == PythonApp.Mode.WSGI and not (app_root / "passenger_wsgi.py").exists():
        raise VZoneAPIException(
            detail=f"passenger_wsgi.py introuvable dans {app_root}. "
            "L'Application root doit contenir passenger_wsgi.py (comme cPanel).",
            code="no_passenger_wsgi",
            status_code=400,
            extra={"root": str(app_root)},
        )

    cmd = _build_start_command(app, app_root, py)
    log_offset = error_log.stat().st_size if error_log.exists() else 0
    try:
        from apps.accounts.linux_users import jail_username_for

        access_f = _open_app_log_append(app.owner, access_log)
        error_f = _open_app_log_append(app.owner, error_log)
        jail = jail_username_for(app.owner)
        spawn_cmd = build_runas_cmd(jail, cmd, env=env)
        proc = subprocess.Popen(
            spawn_cmd,
            cwd=str(app_root),
            stdout=access_f,
            stderr=error_f,
            start_new_session=True,
        )
        # Attendre que le port écoute (gunicorn peut mettre >1s à binder)
        if not _wait_port(app.port, timeout_s=20.0):
            new_log = _log_bytes_since(error_log, log_offset)
            if proc.poll() is not None:
                raise RuntimeError(
                    _format_start_failure(returncode=proc.returncode, stderr_new=new_log)
                )
            _kill_app_pid(proc.pid)
            raise RuntimeError(
                _format_start_failure(returncode=None, stderr_new=new_log, port=app.port)
            )
        if proc.poll() is not None:
            new_log = _log_bytes_since(error_log, log_offset)
            raise RuntimeError(
                _format_start_failure(returncode=proc.returncode, stderr_new=new_log)
            )
        try:
            pid_file.write_text(str(proc.pid), encoding="utf-8")
        except OSError:
            _reclaim_app_logs_for_panel(app.owner, pid_file.parent, pid_file)
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
            new_log = _filter_log_noise(_log_bytes_since(error_log, log_offset))
            extra = {"error": detail, "stderr": new_log[-1500:]}
        if hasattr(exc, "extra") and isinstance(getattr(exc, "extra"), dict):
            extra.update(exc.extra)
        # Ne jamais stocker le bruit scanners WordPress dans last_error ;
        # tronquer depuis la FIN pour garder ModuleNotFoundError / etc.
        detail_clean = _filter_log_noise(detail).strip()
        if not detail_clean:
            detail_clean = (
                "Échec au démarrage (voir logs/error.log et les dépendances du venv)."
            )
        # N'ajoute le hint venv que si ce n'est pas déjà un problème de perms logs
        if "permission denied" not in detail_clean.lower() and "log_permission" not in str(
            getattr(exc, "code", "") or extra.get("code") or ""
        ):
            mismatch = _venv_version_mismatch_hint(venv_dir, app.python_version)
            if mismatch and mismatch.strip() not in detail_clean:
                detail_clean = f"{detail_clean.rstrip()}{mismatch}"
        detail_clean = _clip_end(detail_clean, 900)
        app.status = PythonApp.Status.ERROR
        app.last_error = detail_clean
        app.pid = None
        try:
            if pid_file.exists():
                pid_file.unlink(missing_ok=True)
        except OSError:
            _clear_app_pid_file(app.owner, pid_file)
        app.save()
        write_app_config(app)
        raise VZoneAPIException(
            detail=f"Impossible de démarrer l'application : {_clip_end(detail_clean, 520)}",
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
    pid = _read_app_pid_file(pid_file, app.pid)

    if provision_mode() != "mock" and pid and should_execute():
        _kill_app_pid(pid)

    _clear_app_pid_file(app.owner, pid_file)
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
