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
from apps.core.app_runtime import (
    free_listen_port as _free_listen_port,
    kill_app_pid as _kill_app_pid,
    normalize_app_domain,
    our_process_owns_port as _our_process_owns_port,
    pids_listening_on_port as _pids_listening_on_port,
    port_listening as _port_listening,
    process_alive as _process_alive,
    wait_port as _wait_port,
)
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

            domains = list(
                Domain.objects.filter(name__iexact=name).select_related("owner", "parent")
            )
            if not domains:
                domains = list(
                    Domain.objects.filter(name__iexact=f"www.{name}").select_related(
                        "owner", "parent"
                    )
                )
            # Aussi le www./bare jumeau
            extra_names = {name, f"www.{name}"}
            for d in list(domains):
                for alt in extra_names:
                    if d.name.lower() != alt:
                        twin = (
                            Domain.objects.filter(name__iexact=alt)
                            .select_related("owner", "parent")
                            .first()
                        )
                        if twin and twin not in domains:
                            domains.append(twin)

            if domains:
                for domain in domains:
                    sync_domain_vhost(domain)
                return
            logger.warning(
                "Aucun Domain panel pour %s — sync global (proxy Python peut manquer)",
                name,
            )
        from apps.domains.services import refresh_web_routing

        refresh_web_routing()
    except Exception:  # noqa: BLE001
        logger.exception("refresh_web_routing / sync_domain_vhost a échoué")

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")

# Package Django créé par `django-admin startproject config .` (commande déployée au client).
DJANGO_PROJECT_PACKAGE = "config"

WSGI_TEMPLATE = '''\
"""Entrée WSGI générée par V-zone Panel (compatible cPanel / passenger_wsgi)."""
import os
import sys
import traceback

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
_PROJECT_SUB = "{project_subdir}"
PROJECT_DIR = os.path.join(APP_ROOT, _PROJECT_SUB) if _PROJECT_SUB else APP_ROOT
for _p in (PROJECT_DIR, APP_ROOT):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{settings_module}")

# Domaines autorisés injectés par le panel au Start (évite DisallowedHost)
_vzone_hosts = (
    os.environ.get("VZONE_ALLOWED_HOSTS")
    or os.environ.get("DJANGO_ALLOWED_HOSTS")
    or os.environ.get("ALLOWED_HOSTS")
    or ""
)

try:
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()
    if _vzone_hosts:
        from django.conf import settings as _dj_settings
        _parsed = [h.strip() for h in _vzone_hosts.split(",") if h.strip()]
        if _parsed:
            # Étendre (ne pas écraser * si déjà présent)
            current = list(getattr(_dj_settings, "ALLOWED_HOSTS", []) or [])
            if "*" not in current:
                for h in _parsed:
                    if h not in current:
                        current.append(h)
                _dj_settings.ALLOWED_HOSTS = current
except Exception as _vzone_exc:
    _vzone_tb = traceback.format_exc()
    def application(environ, start_response):
        body = (
            "V-zone WSGI load error (Django non chargé)\\n\\n"
            + str(_vzone_exc)
            + "\\n\\n"
            + _vzone_tb
            + "\\n"
            "Vérifiez : venv (Django installé), DJANGO_SETTINGS_MODULE={settings_module}, "
            "manage.py à côté de passenger_wsgi.py (ou sous-dossier), "
            "puis Restart / Réparer WSGI depuis le panel.\\n"
        ).encode("utf-8", errors="replace")
        start_response(
            "500 Internal Server Error",
            [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))],
        )
        return [body]
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


_SKIP_DJANGO_DIRS = frozenset(
    {"static", "media", "logs", "public", "public_html", "tmp", "venv", ".venv", "node_modules", "__pycache__"}
)


def _package_with_settings(project_dir: Path) -> str | None:
    """Nom du package contenant settings.py sous project_dir (où se trouve manage.py)."""
    if not (project_dir / "manage.py").exists():
        return None
    for child in sorted(project_dir.iterdir()):
        if (
            not child.is_dir()
            or child.name.startswith(".")
            or child.name in _SKIP_DJANGO_DIRS
        ):
            continue
        if (child / "settings.py").exists() or (child / "settings").is_dir():
            return child.name
    return DJANGO_PROJECT_PACKAGE


def resolve_django_layout(app_root: Path) -> tuple[str, str]:
    """
    Retourne (settings_module, project_subdir).
    project_subdir vide = manage.py à la racine de l'application root ;
    sinon sous-dossier relatif où se trouve manage.py.
    """
    pkg = _package_with_settings(app_root)
    if pkg:
        return f"{pkg}.settings", ""
    try:
        children = sorted(app_root.iterdir())
    except OSError:
        children = []
    for child in children:
        if (
            not child.is_dir()
            or child.name.startswith(".")
            or child.name in _SKIP_DJANGO_DIRS
            or child.name == "virtualenv"
        ):
            continue
        pkg = _package_with_settings(child)
        if pkg:
            return f"{pkg}.settings", child.name
    return f"{DJANGO_PROJECT_PACKAGE}.settings", ""


def detect_django_project_package(app_root: Path) -> str:
    """Trouve le package settings (manage.py à la racine ou 1 niveau sous l'app root)."""
    settings_module, _subdir = resolve_django_layout(app_root)
    return settings_module.split(".", 1)[0]


def find_manage_py(app_root: Path) -> Path | None:
    """Chemin manage.py sous l'application root (racine ou 1 sous-dossier)."""
    direct = app_root / "manage.py"
    if direct.is_file():
        return direct
    try:
        children = sorted(app_root.iterdir())
    except OSError:
        return None
    for child in children:
        if not child.is_dir() or child.name.startswith(".") or child.name in _SKIP_DJANGO_DIRS:
            continue
        cand = child / "manage.py"
        if cand.is_file():
            return cand
    return None


def is_passenger_hello_stub(text: str) -> bool:
    """True si passenger_wsgi.py est encore le stub placeholder V-zone."""
    low = (text or "").lower()
    return "hello from v-zone" in low


def passenger_wsgi_needs_sync(text: str, settings_module: str) -> bool:
    """True si le fichier est un stub Hello / mauvais settings / trop ancien."""
    if is_passenger_hello_stub(text):
        return True
    if "get_wsgi_application" not in text:
        return True
    if f'DJANGO_SETTINGS_MODULE", "{settings_module}"' not in text and (
        f"DJANGO_SETTINGS_MODULE', '{settings_module}'" not in text
    ):
        # settings module différent ou absent
        if "DJANGO_SETTINGS_MODULE" not in text:
            return True
        # Si le module détecté n'apparaît pas du tout → resync
        pkg = settings_module.split(".", 1)[0]
        if pkg and f"{pkg}.settings" not in text:
            return True
    return False


def sync_passenger_wsgi(app: PythonApp, app_root: Path | None = None, *, force: bool = False) -> dict:
    """
    Réécrit passenger_wsgi.py pour pointer vers le bon package Django.
    force=True : toujours réécrire (backup .bak). Sinon seulement si stub Hello / settings faux.
    """
    root = app_root or absolute_app_root(app)
    entry = root / "passenger_wsgi.py"
    settings_module, project_subdir = resolve_django_layout(root)
    existing = ""
    if entry.is_file():
        try:
            existing = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            existing = ""
    if not force and existing and not passenger_wsgi_needs_sync(existing, settings_module):
        return {
            "rewritten": False,
            "path": str(entry),
            "settings_module": settings_module,
            "project_subdir": project_subdir,
            "reason": "already_ok",
        }
    content = WSGI_TEMPLATE.format(
        settings_module=settings_module,
        project_subdir=project_subdir,
    )
    if existing:
        bak = root / "passenger_wsgi.py.bak"
        try:
            bak.write_text(existing, encoding="utf-8")
        except OSError:
            pass
    try:
        entry.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise VZoneAPIException(
            detail=(
                f"Impossible d'écrire passenger_wsgi.py ({exc}). "
                "Vérifiez les permissions du dossier Application root."
            ),
            code="passenger_wsgi_write_failed",
            status_code=500,
            extra={"path": str(entry)},
        ) from exc
    _clear_wsgi_bytecode(root)
    try:
        fix_client_paths(app.owner, entry)
    except Exception:  # noqa: BLE001
        logger.debug("chown passenger_wsgi skip", exc_info=True)
    return {
        "rewritten": True,
        "path": str(entry),
        "settings_module": settings_module,
        "project_subdir": project_subdir,
        "backup": str(root / "passenger_wsgi.py.bak") if existing else "",
        "reason": "forced" if force else "stub_or_mismatch",
        "was_hello_stub": is_passenger_hello_stub(existing),
    }


def allocate_port(owner: User) -> int:
    base = int(getattr(settings, "VZONE_PYTHON_PORT_BASE", 8100))
    used = set(PythonApp.objects.filter(port__gt=0).values_list("port", flat=True))
    for offset in range(0, 5000):
        candidate = base + offset
        if candidate not in used:
            return candidate
    raise VZoneAPIException(detail="Aucun port disponible.", code="no_port", status_code=503)


def _parse_python_version_output(text: str) -> str | None:
    """'Python 3.10.12' → '3.10'."""
    m = re.search(r"Python\s+(\d+)\.(\d+)", text or "", re.I)
    if not m:
        return None
    return f"{m.group(1)}.{m.group(2)}"


def _binary_reports_version(binary: str, version: str) -> bool:
    """True si `binary --version` correspond à major.minor demandé."""
    want = (version or "").strip()
    if not want or not binary:
        return False
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    got = _parse_python_version_output((proc.stdout or "") + (proc.stderr or ""))
    return bool(got and got == want)


def discover_system_python_versions() -> list[tuple[str, str]]:
    """
    Versions Python utilisables sur le serveur : [( '3.12', '/usr/bin/python3.12' ), …]
    Ordre : plus récent d'abord.
    """
    found: dict[str, str] = {}
    candidates = [
        "python3.14",
        "python3.13",
        "python3.12",
        "python3.11",
        "python3.10",
        "python3.9",
        "python3",
        "python",
    ]
    if sys.executable:
        candidates.append(sys.executable)
    for name in candidates:
        path = name if (name.startswith("/") or "\\" in name) else shutil.which(name)
        if not path:
            continue
        try:
            proc = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        ver = _parse_python_version_output((proc.stdout or "") + (proc.stderr or ""))
        if ver and ver not in found:
            found[ver] = path
    # Tri décroissant 3.12 > 3.11 > 3.10
    def _key(item: tuple[str, str]) -> tuple[int, int]:
        maj, min_ = item[0].split(".", 1)
        return (int(maj), int(min_))

    return sorted(found.items(), key=_key, reverse=True)


def resolve_python_version(preferred: str) -> tuple[str, str]:
    """
    Retourne (version, binary) pour preferred si dispo, sinon meilleure version système.
    """
    want = (preferred or "3.12").strip() or "3.12"
    available = discover_system_python_versions()
    if not available:
        # Dernier recours : sys.executable même si version inconnue
        return want, sys.executable or "python3"
    for ver, path in available:
        if ver == want:
            return ver, path
    # Preférée absente → bascule sur la plus récente installée
    return available[0]


def python_binary(version: str) -> str:
    """
    Binaire Python pour une version major.minor.
    Ne renvoie JAMAIS python3 générique s'il ne matche pas la version
    (sinon venv « 3.12 » créé avec 3.10).
    """
    configured = getattr(settings, "VZONE_PYTHON_BIN", "") or ""
    if configured:
        if not version or _binary_reports_version(configured, version):
            return configured
    want = (version or "").strip()
    if want:
        exact = shutil.which(f"python{want}")
        if exact and _binary_reports_version(exact, want):
            return exact
        # Fallbacks seulement s'ils matchent vraiment
        for candidate in (f"python{want.split('.')[0]}", "python3", "python", sys.executable):
            path = candidate if candidate == sys.executable else shutil.which(candidate or "")
            if path and _binary_reports_version(path, want):
                return path
        # Pas de binaire exact → resolve (peut différer) ; create_venv doit gérer
        _ver, path = resolve_python_version(want)
        if _ver == want:
            return path
        raise VZoneAPIException(
            detail=(
                f"Python {want} n'est pas installé sur ce serveur. "
                f"Versions dispo : {', '.join(v for v, _ in discover_system_python_versions()) or 'aucune'}. "
                f"Installez python{want}-venv ou choisissez une autre version d'app."
            ),
            code="python_version_missing",
            status_code=400,
            extra={"requested": want, "available": [v for v, _ in discover_system_python_versions()]},
        )
    path = shutil.which("python3") or sys.executable
    return path or "python3"


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
        settings_module, project_subdir = (
            resolve_django_layout(app_root)
            if framework == PythonApp.Framework.DJANGO
            else (f"{DJANGO_PROJECT_PACKAGE}.settings", "")
        )
        content = WSGI_TEMPLATE.format(
            settings_module=settings_module,
            project_subdir=project_subdir,
        )
        # Créer OU remplacer le stub Hello (jamais laisser le placeholder)
        if not entry.exists():
            entry.write_text(content, encoding="utf-8")
        else:
            try:
                existing = entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                existing = ""
            if is_passenger_hello_stub(existing) or (
                framework == PythonApp.Framework.DJANGO and "get_wsgi_application" not in existing
            ):
                try:
                    (app_root / "passenger_wsgi.py.bak").write_text(existing, encoding="utf-8")
                except OSError:
                    pass
                entry.write_text(content, encoding="utf-8")
                _clear_wsgi_bytecode(app_root)
    readme = app_root / "README.vzone.md"
    if not readme.exists():
        readme.write_text(
            "# Application Python V-zone (style cPanel)\n\n"
            f"Mode: {mode}\nFramework: {framework}\n\n"
            "Placez `manage.py` dans ce dossier (Application root), à côté de `passenger_wsgi.py`.\n"
            "Au Start / Restart, le panel remplace le stub « Hello » par un vrai chargeur Django.\n"
            "Bouton « Réparer WSGI » : force la réécriture + redémarrage.\n",
            encoding="utf-8",
        )


def absolute_app_root(app: PythonApp) -> Path:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    return app_root


def resolve_app_venv_dir(app: PythonApp) -> Path:
    """
    Chemin venv réellement utilisable (bin/activate présent).
    Évite source …/3.12/bin/activate alors que l'app a basculé en 3.10.
    """
    candidates: list[Path] = []
    if app.venv_path:
        candidates.append(Path(app.venv_path))
    candidates.append(cpanel_venv_path(app.owner, app.name, app.python_version))
    base = user_home(app.owner) / "virtualenv" / app.name
    if base.is_dir():
        try:
            children = sorted(
                (p for p in base.iterdir() if p.is_dir()),
                key=lambda p: p.name,
                reverse=True,
            )
            candidates.extend(children)
        except OSError:
            pass
    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if (cand / "bin" / "activate").is_file() or (cand / "Scripts" / "activate.bat").is_file():
            return cand
    return candidates[0] if candidates else cpanel_venv_path(
        app.owner, app.name, app.python_version or "3.12"
    )


def enter_command_for(app: PythonApp) -> str:
    """
    Une ligne à coller dans le terminal SSH (cPanel Application Manager) :
    source ~/virtualenv/<app>/<ver>/bin/activate && cd <application_root>
    """
    app_root = absolute_app_root(app)
    venv = resolve_app_venv_dir(app)
    activate = venv / "bin" / "activate"
    return f"source {activate} && cd {app_root}"


def refresh_enter_scripts(app: PythonApp) -> None:
    """Réécrit ENTER.sh / DEPLOY.sh avec le venv actuel (après bascule 3.12→3.10)."""
    try:
        deploy_info(app)
    except Exception:  # noqa: BLE001
        logger.debug("refresh_enter_scripts skip", exc_info=True)


def ensure_client_pip_dirs(owner: User) -> None:
    """Crée ~/.local et ~/.cache owned par le jail (pip user install / cache)."""
    home = user_home(owner)
    for rel in (".local", ".local/lib", ".cache", ".cache/pip"):
        path = home / rel
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
    try:
        from apps.accounts.linux_users import jail_username_for

        jail = jail_username_for(owner)
        fix_client_paths(owner, home / ".local", home / ".cache")
        # Si fix-app-perms refuse hors app, chown via runas touch
        del jail
    except Exception:  # noqa: BLE001
        logger.debug("ensure_client_pip_dirs skip", exc_info=True)


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
    # Ne jamais créer un venv « 3.12 » avec python3=3.10
    if provision_mode() != "mock" and should_execute():
        python_version, _bin = resolve_python_version(python_version)
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
    # Django : passenger_wsgi déjà correct dès la création (pas de stub Hello)
    if mode == PythonApp.Mode.WSGI and (
        framework == PythonApp.Framework.DJANGO or find_manage_py(app_root) is not None
    ):
        try:
            sync_passenger_wsgi(app, app_root, force=True)
        except Exception:  # noqa: BLE001
            logger.debug("sync_passenger_wsgi à la création ignoré", exc_info=True)
    if app.domain_name:
        _claim_app_domain(app, app.domain_name)
        app.refresh_from_db()
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
    if domain_name is not None and app.domain_name:
        _claim_app_domain(app, app.domain_name)
    write_app_config(app)
    # Re-proxifier l'ancien domaine (retour public_html) + le nouveau (vers l'app).
    if domain_name is not None and old_domain and old_domain != app.domain_name:
        _refresh_domain_routing(old_domain)
    _refresh_domain_routing(app.domain_name)
    return app


def install_requirements(app: PythonApp) -> dict:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    req = app_root / (app.requirements_file or "requirements.txt")
    missing_mod = _extract_missing_module(app.last_error or "")
    missing_pkg = _pip_package_for_module(missing_mod) if missing_mod else ""
    if not req.exists() and not missing_pkg:
        raise VZoneAPIException(
            detail=(
                "requirements.txt introuvable et aucun module manquant détecté. "
                "Ajoutez un requirements.txt dans l'application root, "
                "ou démarrez l'app une fois pour capturer le ModuleNotFoundError."
            ),
            code="no_requirements",
            status_code=400,
        )
    venv_dir = resolve_app_venv_dir(app)
    # Aligne venv / version système avant pip
    if provision_mode() != "mock" and should_execute():
        venv_dir, py = _ensure_venv_matches_labeled_version(
            app, app.owner, venv_dir, app.python_version
        )
        refresh_enter_scripts(app)
    else:
        py = venv_python(venv_dir)
    if provision_mode() == "mock" or not py.exists():
        log = app_root / "logs" / "pip.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        parts = []
        if req.exists():
            parts.append(f"mock install -r {req.name}")
        if missing_pkg:
            parts.append(f"mock install {missing_pkg}")
        log.write_text("\n".join(parts) + "\n", encoding="utf-8")
        return {
            "mode": "mock",
            "requirements": str(req) if req.exists() else "",
            "extra_packages": [missing_pkg] if missing_pkg else [],
            "log": str(log),
            "venv": str(venv_dir),
        }
    ensure_client_pip_dirs(app.owner)
    # Ownership avant pip jailé
    fix_client_paths(app.owner, app_root, venv_dir)
    chunks: list[str] = []
    if req.exists():
        try:
            result = _run_as_owner(
                app.owner,
                [str(py), "-m", "pip", "install", "-r", str(req)],
                cwd=app_root,
            )
            chunks.append(f"# pip install -r {req.name}\n{result.stdout}\n{result.stderr}")
        except VZoneAPIException as req_exc:
            chunks.append(f"# pip install -r {req.name} FAILED\n{req_exc.detail}\n")
            if not missing_pkg:
                raise
            logger.warning("pip -r échoué, tentative paquet manquant %s", missing_pkg)
    # Paquet manquant (souvent absent du requirements ou nom PyPI différent)
    if missing_pkg:
        result = _run_as_owner(
            app.owner,
            [str(py), "-m", "pip", "install", missing_pkg],
            cwd=app_root,
        )
        chunks.append(f"# pip install {missing_pkg}\n{result.stdout}\n{result.stderr}")
    log = app_root / "logs" / "pip.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("\n".join(chunks), encoding="utf-8")
    except OSError:
        pass
    fix_client_paths(app.owner, app_root, venv_dir)
    return {
        "mode": "live",
        "requirements": str(req) if req.exists() else "",
        "extra_packages": [missing_pkg] if missing_pkg else [],
        "log": str(log),
        "venv": str(venv_dir),
    }


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
    app: PythonApp,
    owner: User,
    venv_dir: Path,
    labeled_version: str,
) -> tuple[Path, Path]:
    """
    Garantit un venv cohérent avec une version Python réellement installée.

    Retourne (venv_dir, python_binaire_venv).
    Si 3.12 demandé mais seul 3.10 est dispo → bascule app + recree sous …/3.10/.
    """
    # Préfère un venv qui existe vraiment (évite …/3.12 disparu après bascule)
    existing = resolve_app_venv_dir(app)
    if (existing / "bin" / "activate").is_file() or (existing / "pyvenv.cfg").is_file():
        venv_dir = existing
        if str(existing) != (app.venv_path or ""):
            app.venv_path = str(existing)
            # Nom du dossier parent = version (…/virtualenv/app/3.10)
            leaf = existing.name.strip()
            if re.fullmatch(r"\d+\.\d+", leaf):
                app.python_version = leaf
            app.save(update_fields=["venv_path", "python_version", "updated_at"])

    version = (app.python_version or labeled_version or "3.12").strip() or "3.12"
    hint = _venv_version_mismatch_hint(venv_dir, version)

    if not hint and venv_python(venv_dir).exists():
        refresh_enter_scripts(app)
        return venv_dir, venv_python(venv_dir)

    if provision_mode() == "mock":
        return venv_dir, venv_python(venv_dir)

    if not should_execute():
        raise VZoneAPIException(
            detail=(hint or "Venv manquant.").strip(),
            code="venv_version_mismatch",
            status_code=400,
            extra={"venv": str(venv_dir), "expected": version},
        )

    # Version réellement utilisable sur le serveur
    try:
        resolved_ver, _resolved_bin = resolve_python_version(version)
        # Valide que python_binary accepte (exact match)
        py_bin = python_binary(resolved_ver)
    except VZoneAPIException:
        available = discover_system_python_versions()
        if not available:
            raise
        resolved_ver, py_bin = available[0]

    target_dir = venv_dir
    if resolved_ver != version:
        logger.warning(
            "Python %s absent — bascule app %s vers %s (%s)",
            version,
            app.name,
            resolved_ver,
            py_bin,
        )
        target_dir = cpanel_venv_path(owner, app.name, resolved_ver)
        app.python_version = resolved_ver
        app.venv_path = str(target_dir)
        app.save(update_fields=["python_version", "venv_path", "updated_at"])
        # Nettoie l'ancien dossier incohérent (ex. …/3.12/ avec python3.10)
        if venv_dir != target_dir and venv_dir.exists():
            shutil.rmtree(venv_dir, ignore_errors=True)

    # Recrée si absent ou toujours incohérent
    need_recreate = (
        not (target_dir / "pyvenv.cfg").exists()
        or bool(_venv_version_mismatch_hint(target_dir, resolved_ver))
    )
    if need_recreate:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        create_venv(target_dir, resolved_ver)
        fix_client_paths(owner, target_dir, target_dir.parent)

    still = _venv_version_mismatch_hint(target_dir, resolved_ver)
    if still:
        raise VZoneAPIException(
            detail=still.strip(),
            code="venv_version_mismatch",
            status_code=400,
            extra={"venv": str(target_dir), "expected": resolved_ver},
        )

    py = venv_python(target_dir)
    if not py.exists():
        raise VZoneAPIException(
            detail=f"Virtualenv introuvable après recreation : {target_dir}",
            code="venv_missing",
            status_code=400,
            extra={"venv": str(target_dir)},
        )
    if str(target_dir) != (app.venv_path or ""):
        app.venv_path = str(target_dir)
        app.python_version = resolved_ver
        app.save(update_fields=["venv_path", "python_version", "updated_at"])
    refresh_enter_scripts(app)
    return target_dir, py


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


def _extract_missing_module(err: str) -> str | None:
    m = re.search(
        r"ModuleNotFoundError:\s*No module named ['\"]([^'\"]+)['\"]",
        err or "",
    )
    if not m:
        m = re.search(r"No module named ['\"]([^'\"]+)['\"]", err or "")
    if not m:
        return None
    # 'pymysql' ou 'django.db' → paquet top-level
    return m.group(1).split(".")[0].strip() or None


# Import Python → nom PyPI (souvent différent : widget_tweaks ≠ widget_tweaks sur PyPI).
PIP_MODULE_ALIASES: dict[str, str] = {
    "widget_tweaks": "django-widget-tweaks",
    "jazzmin": "django-jazzmin",
    "crispy_forms": "django-crispy-forms",
    "rest_framework": "djangorestframework",
    "corsheaders": "django-cors-headers",
    "allauth": "django-allauth",
    "ckeditor": "django-ckeditor",
    "tinymce": "django-tinymce",
    "import_export": "django-import-export",
    "django_filters": "django-filter",
    "environ": "django-environ",
    "decouple": "python-decouple",
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "OpenSSL": "pyOpenSSL",
    "dateutil": "python-dateutil",
    "jose": "python-jose",
    "jwt": "PyJWT",
    "dotenv": "python-dotenv",
    "MySQLdb": "mysqlclient",
    "pymysql": "PyMySQL",
    "psycopg2": "psycopg2-binary",
    "magic": "python-magic",
}


def _pip_package_for_module(module: str) -> str:
    """Nom à passer à `pip install` pour un module import manquant."""
    name = (module or "").strip()
    if not name:
        return name
    return PIP_MODULE_ALIASES.get(name, name)


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

    def _run_probe() -> subprocess.CompletedProcess:
        from apps.accounts.linux_users import jail_username_for
        from apps.security.runas import build_runas_cmd, runas_available

        probe = [str(py), "-c", probe_py]
        if runas_available():
            jail = jail_username_for(app.owner)
            probe = build_runas_cmd(jail, probe, env=env)
        return subprocess.run(
            probe,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=str(app_root),
        )

    try:
        proc = _run_probe()
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

    # Venv souvent vide après bascule 3.12→3.10 : pip -r puis paquet manquant
    missing = _extract_missing_module(err or (proc.stderr or ""))
    if missing and provision_mode() != "mock" and should_execute():
        pkg = _pip_package_for_module(missing)
        logger.warning(
            "Préflight %s : module `%s` manquant — pip install %s (requirements / paquet)",
            app.name,
            missing,
            pkg,
        )
        ensure_client_pip_dirs(app.owner)
        fix_client_paths(
            app.owner,
            app_root,
            Path(venv_dir) if venv_dir else resolve_app_venv_dir(app),
        )
        req = app_root / (app.requirements_file or "requirements.txt")
        try:
            if req.is_file():
                try:
                    _run_as_owner(
                        app.owner,
                        [str(py), "-m", "pip", "install", "-r", str(req)],
                        cwd=app_root,
                    )
                except VZoneAPIException as req_exc:
                    # requirements incomplet / conflit : on tente quand même le paquet manquant
                    logger.warning("pip -r échoué pour %s : %s", app.name, req_exc.detail)
                    err = f"{err}\nPip -r échoué : {req_exc.detail}"
            # Toujours tenter le paquet manquant : requirements peut l'omettre,
            # et le nom PyPI peut différer du nom d'import (widget_tweaks → django-widget-tweaks).
            if pkg:
                _run_as_owner(
                    app.owner,
                    [str(py), "-m", "pip", "install", pkg],
                    cwd=app_root,
                )
            proc = _run_probe()
            if proc.returncode == 0:
                return
            err = _summarize_traceback((proc.stderr or proc.stdout or "").strip())
        except VZoneAPIException as pip_exc:
            err = f"{err}\nPip auto-install échoué : {pip_exc.detail}"

    hint = _venv_version_mismatch_hint(venv_dir or Path(), app.python_version)
    pip_hint = ""
    if missing:
        pkg = _pip_package_for_module(missing)
        pip_hint = (
            f" Installez dans le venv : `source {resolve_app_venv_dir(app)}/bin/activate "
            f"&& pip install {pkg}`."
        )
    raise VZoneAPIException(
        detail=(
            f"Échec import `{mod}` (avant gunicorn). "
            + (_clip_end(err, 500) if err else "Erreur d'import inconnue.")
            + pip_hint
            + hint
        ),
        code="app_import_failed",
        status_code=400,
        extra={
            "module": mod,
            "stderr": err[-1500:] if err else "",
            "missing": missing or "",
            "pip_package": _pip_package_for_module(missing) if missing else "",
        },
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
        "failed to resolve group",
        "no such process",
        "gid introuvable",
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


# --- port helpers: apps.core.app_runtime (importés en tête de module) ---


def _clear_wsgi_bytecode(app_root: Path) -> None:
    """Supprime les .pyc de passenger_wsgi (évite stub Hello en cache)."""
    for pattern in ("passenger_wsgi*.pyc", "passenger_wsgi*.pyo"):
        for p in app_root.glob(pattern):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
    cache = app_root / "__pycache__"
    if cache.is_dir():
        for p in cache.glob("passenger_wsgi*.pyc"):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def _local_app_response_body(port: int, *, timeout: float = 4.0) -> str:
    """Corps HTTP de GET / sur 127.0.0.1:port (pour détecter le stub Hello)."""
    if port <= 0:
        return ""
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{port}/"
    try:
        req = urllib.request.Request(url, method="GET", headers={"Host": "127.0.0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(4096)
            return raw.decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        # HTTPError peut contenir un body (500 Django)
        if isinstance(exc, urllib.error.HTTPError):
            try:
                return (exc.read(4096) or b"").decode("utf-8", errors="replace")
            except OSError:
                return ""
        return ""


def _response_is_hello_stub(body: str) -> bool:
    return "hello from v-zone" in (body or "").lower()


def _repair_wsgi_for_start(app: PythonApp, app_root: Path) -> dict:
    """
    Réécrit passenger_wsgi.py si stub Hello / Django, purge le bytecode.
    force=True dès qu'un Hello est détecté (sinon sync intelligent).
    """
    if app.mode != PythonApp.Mode.WSGI:
        return {"rewritten": False, "reason": "not_wsgi"}
    entry = app_root / "passenger_wsgi.py"
    stub_text = ""
    if entry.is_file():
        try:
            stub_text = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            stub_text = ""
    is_hello = is_passenger_hello_stub(stub_text)
    djangoish = (
        app.framework == PythonApp.Framework.DJANGO
        or find_manage_py(app_root) is not None
    )
    info: dict = {
        "rewritten": False,
        "was_hello": is_hello,
        "path": str(entry),
    }
    if not (is_hello or djangoish):
        return {**info, "reason": "skip_non_django"}
    # Toujours réécrire pour Django / Hello : un gunicorn orphelin + vieux fichier = Hello éternel
    info = sync_passenger_wsgi(app, app_root, force=True)
    after = ""
    if entry.is_file():
        try:
            after = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            after = ""
    _clear_wsgi_bytecode(app_root)
    if is_passenger_hello_stub(after):
        manage = find_manage_py(app_root)
        raise VZoneAPIException(
            detail=(
                "Impossible d'écraser le stub « Hello from V-zone Python app » dans "
                f"{entry}. "
                + (
                    f"manage.py trouvé : {manage}. "
                    if manage
                    else "Aucun manage.py dans l'Application root. "
                )
                + "Vérifiez les permissions (sudo vzone-fix-app-perms), "
                "puis Réparer WSGI."
            ),
            code="passenger_wsgi_hello_stub",
            status_code=400,
            extra={"root": str(app_root), "manage_py": str(manage) if manage else ""},
        )
    return info


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


def _claim_app_domain(app: PythonApp, domain_name: str) -> None:
    """Un domaine = une app Python (priorité Django/proxy sur public_html)."""
    name = normalize_app_domain(domain_name)
    if not name:
        return
    # Libérer le domaine sur les autres apps du même owner (et globalement même hostname)
    PythonApp.objects.filter(domain_name__iexact=name).exclude(pk=app.pk).update(domain_name="")
    PythonApp.objects.filter(domain_name__iexact=f"www.{name}").exclude(pk=app.pk).update(
        domain_name=""
    )
    try:
        from apps.node_apps.models import NodeApp

        NodeApp.objects.filter(domain_name__iexact=name).update(domain_name="")
        NodeApp.objects.filter(domain_name__iexact=f"www.{name}").update(domain_name="")
    except Exception:  # noqa: BLE001
        pass


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

    # Domaine → ALLOWED_HOSTS (Django / apps qui lisent ces vars)
    domain = normalize_app_domain(app.domain_name or "")
    hosts = ["*", "localhost", "127.0.0.1"]
    if domain:
        hosts.extend([domain, f"www.{domain}"])
        env["VIRTUAL_HOST"] = domain
    host_csv = ",".join(dict.fromkeys(hosts))
    env["VZONE_ALLOWED_HOSTS"] = host_csv
    env["DJANGO_ALLOWED_HOSTS"] = host_csv
    env["ALLOWED_HOSTS"] = host_csv

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
    """db.sqlite3 et cousins à la racine + sous-dossiers courants (+ 1 niveau)."""
    found: list[Path] = []
    patterns = ("*.sqlite3", "*.sqlite", "*.db")
    if not app_root.exists():
        return found
    for pat in patterns:
        found.extend(app_root.glob(pat))
    for sub in ("data", "var", "db", "database", "databases", "config", "project"):
        d = app_root / sub
        if d.is_dir():
            for pat in patterns:
                found.extend(d.glob(pat))
                # Un niveau de plus (ex. project/data/db.sqlite3)
                try:
                    for child in d.iterdir():
                        if child.is_dir():
                            found.extend(child.glob(pat))
                except OSError:
                    pass
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

    SQLite exige aussi le DOSSIER parent en écriture (fichiers -wal/-shm).
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

    # Toujours inclure le root app à vérifier + chaque sqlite trouvé
    if verify_sqlite_in is not None:
        vr = Path(verify_sqlite_in)
        if vr.exists():
            key = str(vr.resolve()) if vr.exists() else str(vr)
            if key not in seen:
                seen.add(key)
                unique.append(vr)
            for db in _iter_sqlite_files(vr):
                dk = str(db.resolve()) if db.exists() else str(db)
                if dk not in seen:
                    seen.add(dk)
                    unique.append(db)

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
                # Toujours --force d'abord (évite exit 5 / Start bloqué)
                proc = subprocess.run(
                    ["sudo", "-n", str(FIX_APP_PERMS), jail, str(path), "--force"],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                if proc.returncode != 0:
                    proc = subprocess.run(
                        ["sudo", "-n", str(FIX_APP_PERMS), jail, str(path)],
                        capture_output=True,
                        text=True,
                        timeout=180,
                        check=False,
                    )
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or "")[:600]
                    logger.warning("fix-app-perms %s %s → %s %s", jail, path, proc.returncode, err)
                    # Ne plus lever : le Start doit pouvoir continuer
                else:
                    logger.info("fix-app-perms OK %s → %s", jail, path)
            except VZoneAPIException:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("fix-app-perms exception: %s", exc)

    # Complément ACL/chmod (sans root)
    for path in unique:
        _grant_jail_write(path, jail, is_dir=path.is_dir())
        if path.is_dir():
            for db in _iter_sqlite_files(path):
                _grant_jail_write(db, jail, is_dir=False)
                _grant_jail_write(db.parent, jail, is_dir=True)

    check_root = verify_sqlite_in
    if check_root is None:
        return
    check_root = Path(check_root)
    if not check_root.exists():
        return

    # Le helper root vérifie déjà l'écriture (runuser). Un 2ᵉ probe via Pulse/runas
    # produisait des faux « readonly » → Start bloqué → nginx reste sur public_html.
    # Soft only : --force si besoin, jamais d'exception sqlite_readonly ici.
    try:
        import shlex

        probe_file = check_root / f".vzone_wprobe_{os.getpid()}"
        db_main = check_root / "db.sqlite3"
        script = (
            f"touch {shlex.quote(str(probe_file))} && rm -f {shlex.quote(str(probe_file))}"
        )
        if db_main.exists():
            script += f" && test -w {shlex.quote(str(db_main))}"

        ok = False
        for runuser_bin in ("/usr/sbin/runuser", "/sbin/runuser"):
            if not Path(runuser_bin).is_file():
                continue
            proc = subprocess.run(
                ["sudo", "-n", runuser_bin, "-u", jail, "--", "/bin/bash", "-c", script],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            if proc.returncode == 0:
                ok = True
            break
        if ok:
            return

        if FIX_APP_PERMS.is_file():
            force = subprocess.run(
                ["sudo", "-n", str(FIX_APP_PERMS), jail, str(check_root), "--force"],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if force.returncode == 0:
                logger.warning(
                    "SQLite/app: --force appliqué pour %s (%s)",
                    jail,
                    check_root,
                )
                return
        logger.warning(
            "SQLite probe soft échoué pour %s @ %s — Start continué (perms déjà fixés)",
            jail,
            check_root,
        )
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
        stderr = getattr(exc, "stderr", None) or ""
        stdout = getattr(exc, "stdout", None) or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        detail_tail = _clip_end((stderr or stdout or str(exc)).strip(), 420)
        # Aide lisible pour pip (No matching distribution, etc.)
        raise VZoneAPIException(
            detail=f"Échec commande Python (jail) : {detail_tail or str(exc)}",
            code="python_cmd_failed",
            status_code=502,
            extra={"stderr": stderr[-2000:] if stderr else str(exc), "cmd": full},
        ) from exc


def _ensure_django_hosts_patch(app: PythonApp, app_root: Path) -> None:
    """
    Garantit que Django accepte le domaine panel.
    - Si passenger_wsgi.py est encore l'ancien template, on y injecte le patch ALLOWED_HOSTS.
    - Sinon on étend ALLOWED_HOSTS dans settings.py si trop restrictif (localhost only).
    """
    if app.framework != PythonApp.Framework.DJANGO and app.mode != PythonApp.Mode.WSGI:
        return
    domain = normalize_app_domain(app.domain_name or "")
    wsgi = app_root / "passenger_wsgi.py"
    marker = "VZONE_ALLOWED_HOSTS"
    try:
        if wsgi.is_file():
            text = wsgi.read_text(encoding="utf-8", errors="replace")
            if marker not in text and "get_wsgi_application" in text:
                # Patch post-application : ajouter à la fin du fichier
                append = (
                    "\n# --- V-zone: étendre ALLOWED_HOSTS depuis l'env panel ---\n"
                    "try:\n"
                    f"    _vh = os.environ.get({marker!r}) or os.environ.get('DJANGO_ALLOWED_HOSTS') or ''\n"
                    "    if _vh:\n"
                    "        from django.conf import settings as _s\n"
                    "        _hosts = [h.strip() for h in _vh.split(',') if h.strip()]\n"
                    "        _cur = list(getattr(_s, 'ALLOWED_HOSTS', []) or [])\n"
                    "        if '*' not in _cur:\n"
                    "            for _h in _hosts:\n"
                    "                if _h not in _cur:\n"
                    "                    _cur.append(_h)\n"
                    "            _s.ALLOWED_HOSTS = _cur\n"
                    "except Exception:\n"
                    "    pass\n"
                )
                if append.strip() not in text:
                    wsgi.write_text(text.rstrip() + "\n" + append, encoding="utf-8")
        # settings.py : si ALLOWED_HOSTS = [] ou localhost only, élargir
        pkg = detect_django_project_package(app_root)
        settings_py = app_root / pkg / "settings.py"
        if settings_py.is_file() and domain:
            st = settings_py.read_text(encoding="utf-8", errors="replace")
            if "VZONE_HOSTS_PATCH" not in st:
                patch = (
                    "\n# VZONE_HOSTS_PATCH — domaines panel (ne pas supprimer)\n"
                    "import os as _vzone_os\n"
                    "_vzone_extra = _vzone_os.environ.get('VZONE_ALLOWED_HOSTS', '')\n"
                    "if _vzone_extra:\n"
                    "    ALLOWED_HOSTS = list(dict.fromkeys(\n"
                    "        list(ALLOWED_HOSTS) + [h.strip() for h in _vzone_extra.split(',') if h.strip()]\n"
                    "    ))\n"
                )
                settings_py.write_text(st.rstrip() + "\n" + patch, encoding="utf-8")
    except OSError as exc:
        logger.debug("django hosts patch skip: %s", exc)


def _ensure_app_data_writable(owner: User, app_root: Path, *extra: Path) -> None:
    """Garantie ownership jail avant démarrage gunicorn.

    Ne bloque plus le Start : un échec de perms ne doit pas empêcher gunicorn
    (sinon le domaine reste sur public_html). On force au maximum via --force.
    """
    jail = _jail_name(owner)
    # Toujours tenter --force en premier (idempotent)
    if (
        provision_mode() != "mock"
        and jail
        and FIX_APP_PERMS.is_file()
        and app_root.exists()
    ):
        try:
            subprocess.run(
                ["sudo", "-n", str(FIX_APP_PERMS), jail, str(app_root), "--force"],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except Exception:  # noqa: BLE001
            logger.warning("fix-app-perms --force skip", exc_info=True)
    fix_client_paths(
        owner,
        app_root,
        *extra,
        required=False,
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
    # Effacer l'ancienne erreur affichée dans l'UI (ex. faux SQLite readonly)
    if app.last_error:
        app.last_error = ""
        app.save(update_fields=["last_error", "updated_at"])
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    venv_dir = Path(app.venv_path) if app.venv_path else cpanel_venv_path(app.owner, app.name, app.python_version)
    venv_dir, py = _ensure_venv_matches_labeled_version(
        app, app.owner, venv_dir, app.python_version
    )
    ensure_client_pip_dirs(app.owner)
    refresh_enter_scripts(app)
    access_log, error_log = _prepare_app_logs(app.owner, app_root)
    _ensure_app_data_writable(app.owner, app_root, venv_dir)

    # Toujours réparer le stub Hello AVANT mock / hosts patch / gunicorn
    try:
        _repair_wsgi_for_start(app, app_root)
    except VZoneAPIException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("repair wsgi start %s", app.name)
        raise VZoneAPIException(
            detail=f"Échec réparation passenger_wsgi.py : {exc}",
            code="passenger_wsgi_sync_failed",
            status_code=500,
        ) from exc

    _ensure_django_hosts_patch(app, app_root)
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

    # Arrêter une instance précédente + libérer le port (orphans gunicorn)
    if app.pid or pid_file.exists():
        try:
            stop_python_app(app)
            app.refresh_from_db()
        except Exception:  # noqa: BLE001
            logger.debug("stop avant start ignoré", exc_info=True)
    _free_listen_port(app.port)

    ensure_runtime_deps(app, app_root, py)
    # 2e passe : au cas où pip / perms auraient restauré un vieux fichier
    _repair_wsgi_for_start(app, app_root)
    _preflight_runtime_module(app, py)
    _preflight_app_import(app, app_root, py, env, venv_dir=venv_dir)
    # Préflight / pip peuvent recréer des fichiers owned par le panel → re-fix
    _ensure_app_data_writable(app.owner, app_root, venv_dir)

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
                _free_listen_port(app.port)
                raise RuntimeError(
                    _format_start_failure(returncode=proc.returncode, stderr_new=new_log)
                )
            _kill_app_pid(proc.pid)
            _free_listen_port(app.port)
            raise RuntimeError(
                _format_start_failure(returncode=None, stderr_new=new_log, port=app.port)
            )
        # Le port peut être « ouvert » par un orphelin : notre process doit être vivant + owner
        if proc.poll() is not None:
            new_log = _log_bytes_since(error_log, log_offset)
            holders = _pids_listening_on_port(app.port)
            _free_listen_port(app.port)
            hint = ""
            if "Address already in use" in (new_log or "") or "Connection in use" in (new_log or ""):
                hint = (
                    f" Port {app.port} était déjà pris"
                    + (f" (pids {holders})" if holders else "")
                    + ". Relancez Start après mise à jour (≥ 0.39.11, vzone-kill-port)."
                )
            raise RuntimeError(
                _format_start_failure(returncode=proc.returncode, stderr_new=new_log) + hint
            )
        if not _our_process_owns_port(proc.pid, app.port):
            holders = _pids_listening_on_port(app.port)
            _kill_app_pid(proc.pid)
            _free_listen_port(app.port)
            raise RuntimeError(
                f"Port {app.port} occupé par un autre process {holders or '(inconnu)'} "
                "(souvent un ancien gunicorn Hello). "
                "Mettez à jour le panel (≥ 0.39.11) puis Redémarrer / Réparer WSGI."
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

        # Vérifier que le process ne sert plus le stub Hello (gunicorn orphelin)
        time.sleep(0.4)
        body = _local_app_response_body(app.port)
        if _response_is_hello_stub(body):
            logger.warning(
                "Port %s répond encore Hello stub pour %s — force rewrite + relaunch",
                app.port,
                app.name,
            )
            _kill_app_pid(proc.pid)
            _free_listen_port(app.port)
            sync_passenger_wsgi(app, app_root, force=True)
            _clear_wsgi_bytecode(app_root)
            # Confirmer que le fichier n'est plus Hello
            entry = app_root / "passenger_wsgi.py"
            disk = entry.read_text(encoding="utf-8", errors="replace") if entry.is_file() else ""
            if is_passenger_hello_stub(disk):
                raise RuntimeError(
                    "passenger_wsgi.py contient encore « Hello from V-zone Python app » "
                    f"dans {entry}. Impossible de le réécrire (permissions ?)."
                )
            if _port_listening(app.port):
                _free_listen_port(app.port)
            access_f = _open_app_log_append(app.owner, access_log)
            error_f = _open_app_log_append(app.owner, error_log)
            log_offset = error_log.stat().st_size if error_log.exists() else 0
            spawn_cmd = build_runas_cmd(jail, cmd, env=env)
            proc = subprocess.Popen(
                spawn_cmd,
                cwd=str(app_root),
                stdout=access_f,
                stderr=error_f,
                start_new_session=True,
            )
            if not _wait_port(app.port, timeout_s=20.0) or proc.poll() is not None:
                new_log = _log_bytes_since(error_log, log_offset)
                _kill_app_pid(proc.pid)
                _free_listen_port(app.port)
                raise RuntimeError(
                    _format_start_failure(returncode=proc.poll(), stderr_new=new_log, port=app.port)
                    + " (relance après Hello stub)"
                )
            if not _our_process_owns_port(proc.pid, app.port):
                _kill_app_pid(proc.pid)
                _free_listen_port(app.port)
                raise RuntimeError(
                    f"Port {app.port} toujours pris après kill — "
                    "exécutez: sudo /usr/local/sbin/vzone-kill-port "
                    f"{app.port} puis Restart."
                )
            time.sleep(0.4)
            body2 = _local_app_response_body(app.port)
            if _response_is_hello_stub(body2):
                _kill_app_pid(proc.pid)
                _free_listen_port(app.port)
                raise RuntimeError(
                    "Le site répond encore « Hello from V-zone Python app » après réparation. "
                    f"Vérifiez que gunicorn charge {app_root / 'passenger_wsgi.py'} "
                    "(Application root / entrypoint), puis Relancer."
                )
            try:
                pid_file.write_text(str(proc.pid), encoding="utf-8")
            except OSError:
                _reclaim_app_logs_for_panel(app.owner, pid_file.parent, pid_file)
                pid_file.write_text(str(proc.pid), encoding="utf-8")
            app.pid = proc.pid
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

    if provision_mode() != "mock" and should_execute():
        if pid:
            _kill_app_pid(pid)
        # Toujours libérer le port (évite Hello servi par un gunicorn orphelin)
        if app.port:
            _free_listen_port(app.port)

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


_PAGE_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")


def _django_project_root(app_root: Path) -> tuple[Path, str]:
    """Retourne (répertoire manage.py, nom package settings)."""
    settings_module, subdir = resolve_django_layout(app_root)
    pkg = settings_module.split(".", 1)[0]
    project = app_root / subdir if subdir else app_root
    if not (project / "manage.py").is_file():
        raise VZoneAPIException(
            detail="Projet Django introuvable (manage.py manquant).",
            code="django_missing",
            status_code=404,
        )
    return project, pkg


def _ensure_line_in_list(text: str, *, list_name: str, item: str) -> tuple[str, bool]:
    """Ajoute item dans list_name = [...] si absent."""
    if re.search(rf"['\"]{re.escape(item)}['\"]", text):
        return text, False
    pattern = rf"({list_name}\s*=\s*\[)"
    m = re.search(pattern, text)
    if not m:
        return text, False
    insert_at = m.end()
    addition = f"\n    '{item}',"
    return text[:insert_at] + addition + text[insert_at:], True


def _ensure_url_include(text: str, *, include_path: str, route: str = "") -> tuple[str, bool]:
    """Ajoute path('…', include('…')) dans urlpatterns si absent."""
    marker = f"include('{include_path}')"
    if marker in text or f'include("{include_path}")' in text:
        return text, False
    if "from django.urls import" in text and "include" not in text:
        text = re.sub(
            r"from django\.urls import ([^\n]+)",
            lambda m: (
                m.group(0)
                if "include" in m.group(1)
                else f"from django.urls import include, {m.group(1).strip()}"
            ),
            text,
            count=1,
        )
    elif "from django.urls import" not in text:
        text = "from django.urls import include, path\n" + text
    route_arg = f"'{route}'" if route else "''"
    snippet = f"\n    path({route_arg}, include('{include_path}')),"
    m = re.search(r"(urlpatterns\s*=\s*\[)", text)
    if not m:
        text += f"\nurlpatterns = [{snippet}\n]\n"
        return text, True
    return text[: m.end()] + snippet + text[m.end() :], True


def _find_django_nav_templates(root: Path, *, limit: int = 12) -> list[Path]:
    """Cherche base.html / nav / header susceptibles de contenir le menu."""
    if not root.is_dir():
        return []
    preferred_names = {
        "base.html",
        "navbar.html",
        "nav.html",
        "header.html",
        "navigation.html",
        "menu.html",
    }
    hits: list[Path] = []
    try:
        for path in root.rglob("*.html"):
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            parts = {p.lower() for p in rel.parts}
            if parts & {"venv", ".venv", "node_modules", "__pycache__", "static", "migrations"}:
                continue
            name = path.name.lower()
            if name not in preferred_names and "base" not in name and "nav" not in name:
                continue
            hits.append(path)
            if len(hits) >= 40:
                break
    except OSError:
        return []

    def _score(p: Path) -> tuple[int, str]:
        name = p.name.lower()
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")[:8000].lower()
        except OSError:
            text = ""
        score = 0
        if name == "base.html":
            score += 50
        if "nav" in name or "menu" in name or "header" in name:
            score += 30
        if "<nav" in text or "navbar" in text or "nav-item" in text or "nav-link" in text:
            score += 40
        if "</ul>" in text and ("nav" in text or "menu" in text):
            score += 20
        if "client" in str(p).lower():
            score += 5
        return (-score, str(p).lower())

    hits.sort(key=_score)
    return hits[:limit]


def _nav_link_html(slug: str, title: str, *, bootstrap: bool) -> str:
    label = title or slug.title()
    href = f"{{% url '{slug}' %}}"
    if bootstrap:
        return (
            f'    <li class="nav-item">\n'
            f'      <a class="nav-link" href="{href}">{label}</a>\n'
            f"    </li>\n"
        )
    return f'    <a class="vz-nav-link" href="{href}">{label}</a>\n'


def _inject_nav_link_into_html(text: str, *, slug: str, title: str) -> tuple[str, bool]:
    """Insère le lien menu si absent. Retourne (html, modified)."""
    markers = (
        f"url '{slug}'",
        f'url "{slug}"',
        f"/{slug}/",
        f"href=\"/{slug}\"",
        f"href='/{slug}'",
    )
    low = text.lower()
    if any(m.lower() in low for m in markers) and (slug in low):
        # Déjà un lien vers cette page
        if f"url '{slug}'" in text or f'url "{slug}"' in text or f"/{slug}/" in text:
            return text, False

    bootstrap = "nav-item" in text or "nav-link" in text or "navbar" in text.lower()
    snippet = _nav_link_html(slug, title, bootstrap=bootstrap)

    # 1) Avant </ul> dans un bloc nav/navbar
    for m in re.finditer(r"</ul\s*>", text, flags=re.IGNORECASE):
        start = max(0, m.start() - 800)
        window = text[start : m.start()].lower()
        if any(k in window for k in ("nav", "menu", "navbar", "nav-item", "nav-link")):
            return text[: m.start()] + snippet + text[m.start() :], True

    # 2) Avant </nav>
    m = re.search(r"</nav\s*>", text, flags=re.IGNORECASE)
    if m:
        return text[: m.start()] + snippet + text[m.start() :], True

    # 3) Après le dernier nav-link / nav-item
    matches = list(re.finditer(r"</(?:li|a)\s*>", text, flags=re.IGNORECASE))
    for m in reversed(matches):
        start = max(0, m.start() - 200)
        if "nav-" in text[start : m.end()].lower():
            return text[: m.end()] + "\n" + snippet + text[m.end() :], True

    # 4) Fallback : juste après <body>
    m = re.search(r"<body[^>]*>", text, flags=re.IGNORECASE)
    if m:
        bar = (
            '\n<nav class="vz-auto-nav" style="padding:.75rem 1rem;background:#1f4d2e;">\n'
            f'{snippet}'
            "</nav>\n"
        )
        return text[: m.end()] + bar + text[m.end() :], True

    return text + "\n" + snippet, True


def inject_django_page_into_nav(
    project: Path,
    *,
    slug: str,
    title: str,
    extra_roots: list[Path] | None = None,
) -> dict:
    """
    Ajoute le bouton / lien de la page dans le(s) template(s) de navigation du site.
    Cherche base.html / navbar sous le projet Django (ex. client/templates/…/base.html).
    """
    roots = [project]
    for r in extra_roots or []:
        if r not in roots:
            roots.append(r)
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(_find_django_nav_templates(root))
    # Déduplique en gardant l'ordre (meilleurs scores d'abord par root)
    seen: set[str] = set()
    unique: list[Path] = []
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    patched: list[str] = []
    skipped: list[str] = []
    for path in unique[:8]:
        try:
            original = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        updated, changed = _inject_nav_link_into_html(original, slug=slug, title=title)
        if not changed:
            skipped.append(str(path))
            continue
        try:
            path.write_text(updated, encoding="utf-8")
            patched.append(str(path))
        except OSError as exc:
            skipped.append(f"{path}: {exc}")
        # Un seul template principal suffit en général
        if patched:
            break

    return {
        "nav_patched": patched,
        "nav_skipped": skipped[:10],
        "nav_candidates": [str(p) for p in unique[:8]],
    }


def add_django_dynamic_page(
    app: PythonApp,
    *,
    slug: str,
    title: str = "",
    restart: bool = True,
    add_to_nav: bool = True,
) -> dict:
    """
    Ajoute une page Django dynamique /{slug}/ sur une app Python (vue + template + URL).
    Par défaut, injecte aussi le lien dans le menu (base.html / navbar).
    Appliqué immédiatement sur le disque ; redémarre l'app pour que ce soit live.
    """
    slug = (slug or "").strip().lower().strip("/")
    if not _PAGE_SLUG_RE.match(slug):
        raise VZoneAPIException(
            detail="Slug invalide (ex: lievin, a-propos).",
            code="invalid_slug",
            status_code=400,
        )
    title = (title or slug.replace("-", " ").replace("_", " ").title()).strip()[:120]
    app_root = absolute_app_root(app)
    project, pkg = _django_project_root(app_root)
    pages_pkg = "vz_pages"
    pages_dir = project / pages_pkg
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "__init__.py").write_text("", encoding="utf-8")
    (pages_dir / "apps.py").write_text(
        "from django.apps import AppConfig\n\n\n"
        f"class VzPagesConfig(AppConfig):\n"
        f"    default_auto_field = 'django.db.models.BigAutoField'\n"
        f"    name = '{pages_pkg}'\n",
        encoding="utf-8",
    )

    views_path = pages_dir / "views.py"
    view_fn = f"page_{slug.replace('-', '_')}"
    view_block = (
        f"\ndef {view_fn}(request):\n"
        f"    \"\"\"Page dynamique V-zone : /{slug}/\"\"\"\n"
        f"    from django.utils import timezone\n"
        f"    return render(\n"
        f"        request,\n"
        f"        '{pages_pkg}/{slug}.html',\n"
        f"        {{\n"
        f"            'title': {title!r},\n"
        f"            'slug': {slug!r},\n"
        f"            'now': timezone.now(),\n"
        f"            'path': request.path,\n"
        f"            'host': request.get_host(),\n"
        f"        }},\n"
        f"    )\n"
    )
    if views_path.is_file():
        existing = views_path.read_text(encoding="utf-8", errors="replace")
        if f"def {view_fn}(" not in existing:
            if "from django.shortcuts import render" not in existing:
                existing = "from django.shortcuts import render\n" + existing
            views_path.write_text(existing.rstrip() + "\n" + view_block, encoding="utf-8")
    else:
        views_path.write_text(
            "from django.shortcuts import render\n" + view_block,
            encoding="utf-8",
        )

    urls_app = pages_dir / "urls.py"
    path_line = f"    path('{slug}/', views.{view_fn}, name='{slug}'),\n"
    if urls_app.is_file():
        u = urls_app.read_text(encoding="utf-8", errors="replace")
        if f"name='{slug}'" not in u and f'name="{slug}"' not in u:
            if "urlpatterns" not in u:
                u = (
                    "from django.urls import path\n"
                    "from . import views\n\n"
                    "urlpatterns = [\n"
                    f"{path_line}"
                    "]\n"
                )
            else:
                u = u.replace("urlpatterns = [", "urlpatterns = [\n" + path_line, 1)
            urls_app.write_text(u, encoding="utf-8")
    else:
        urls_app.write_text(
            "from django.urls import path\n"
            "from . import views\n\n"
            "urlpatterns = [\n"
            f"{path_line}"
            "]\n",
            encoding="utf-8",
        )

    tmpl_dir = project / "templates" / pages_pkg
    tmpl_dir.mkdir(parents=True, exist_ok=True)
    (tmpl_dir / f"{slug}.html").write_text(
        "<!DOCTYPE html>\n"
        '<html lang="fr">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        "  <title>{{ title }}</title>\n"
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "  <style>\n"
        "    :root { --ink:#14201a; --moss:#2f6b45; --sand:#f4efe6; }\n"
        "    body { margin:0; font-family:Georgia,serif; background:var(--sand); color:var(--ink); }\n"
        "    header { background:linear-gradient(135deg,var(--moss),#1f4d2e); color:#fff;\n"
        "      padding:3rem 1.5rem 2rem; }\n"
        "    main { max-width:42rem; margin:0 auto; padding:2rem 1.5rem 4rem; }\n"
        "    .meta { opacity:.85; font-size:.95rem; margin-top:.75rem; }\n"
        "    .card { background:#fff; border-radius:12px; padding:1.25rem 1.5rem;\n"
        "      box-shadow:0 8px 24px rgba(20,32,26,.08); margin-top:1.5rem; }\n"
        "    a { color:var(--moss); }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <header>\n"
        "    <h1>{{ title }}</h1>\n"
        "    <p class=\"meta\">Page dynamique Django · {{ path }} · {{ host }}</p>\n"
        "  </header>\n"
        "  <main>\n"
        "    <div class=\"card\">\n"
        f"      <p>Bienvenue sur la page <strong>{slug}</strong>.</p>\n"
        "      <p>Générée le {{ now|date:\"d/m/Y H:i\" }} (timezone serveur).</p>\n"
        "      <p><a href=\"/\">← Retour accueil</a></p>\n"
        "    </div>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n",
        encoding="utf-8",
    )

    steps: list[str] = [f"view:{view_fn}", f"template:{slug}.html"]
    nav_info: dict = {}

    settings_file = project / pkg / "settings.py"
    if settings_file.is_file():
        s = settings_file.read_text(encoding="utf-8", errors="replace")
        s2, added_app = _ensure_line_in_list(s, list_name="INSTALLED_APPS", item=pages_pkg)
        if added_app:
            settings_file.write_text(s2, encoding="utf-8")
            steps.append("installed_apps")
            s = s2
        # TEMPLATES DIRS → project/templates
        if "TEMPLATES" in s and "BASE_DIR" in s and str(tmpl_dir.parent) not in s:
            if "DIRS': []" in s or 'DIRS": []' in s:
                s = s.replace("DIRS': []", "DIRS': [BASE_DIR / 'templates']", 1)
                s = s.replace('DIRS": []', 'DIRS": [BASE_DIR / "templates"]', 1)
                settings_file.write_text(s, encoding="utf-8")
                steps.append("templates_dirs")

    urls_main = project / pkg / "urls.py"
    if urls_main.is_file():
        u = urls_main.read_text(encoding="utf-8", errors="replace")
        u2, added_inc = _ensure_url_include(u, include_path=f"{pages_pkg}.urls")
        if added_inc:
            urls_main.write_text(u2, encoding="utf-8")
            steps.append("urls_include")

    if add_to_nav:
        nav_info = inject_django_page_into_nav(
            project,
            slug=slug,
            title=title,
            extra_roots=[app_root],
        )
        if nav_info.get("nav_patched"):
            steps.append("nav:" + ",".join(Path(p).name for p in nav_info["nav_patched"]))
        else:
            steps.append("nav_not_found")

    fix_client_paths(app.owner, pages_dir, tmpl_dir, project / pkg)
    for p in nav_info.get("nav_patched") or []:
        try:
            fix_client_paths(app.owner, Path(p).parent)
        except Exception:  # noqa: BLE001
            pass

    restarted = False
    if restart and app.is_active:
        try:
            restart_python_app(app)
            restarted = True
            steps.append("app_restarted")
        except Exception as exc:  # noqa: BLE001
            logger.warning("restart after django page skip: %s", exc)
            steps.append(f"restart_skip:{exc}")

    domain = (app.domain_name or "").strip()
    page_url = f"https://{domain}/{slug}/" if domain else f"/{slug}/"
    nav_ok = bool(nav_info.get("nav_patched"))
    return {
        "app_id": app.pk,
        "app_name": app.name,
        "slug": slug,
        "title": title,
        "page_url": page_url,
        "path": f"/{slug}/",
        "project": str(project),
        "restarted": restarted,
        "add_to_nav": add_to_nav,
        "nav_patched": nav_info.get("nav_patched") or [],
        "nav_candidates": nav_info.get("nav_candidates") or [],
        "steps": steps,
        "message": (
            f"Page dynamique « {title} » ajoutée sur {app.name} → {page_url}"
            + (
                f" + bouton menu dans {Path(nav_info['nav_patched'][0]).name}"
                if nav_ok
                else " (menu : aucun base.html/nav trouvé à patcher)"
            )
            + f"{' · app redémarrée' if restarted else ''}."
        ),
    }


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
