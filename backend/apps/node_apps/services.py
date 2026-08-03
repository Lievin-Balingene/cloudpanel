"""Services applications Node.js : scaffold, npm, start/stop, logs."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.files.services import user_home
from apps.node_apps.models import NodeApp

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")

SERVER_JS = """\
const http = require("http");
const port = process.env.PORT || 3000;
const server = http.createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ ok: true, panel: "vzone" }));
});
server.listen(port, "127.0.0.1", () => {
  console.log(`V-zone Node app listening on ${port}`);
});
"""

EXPRESS_SERVER = """\
const http = require("http");
const port = process.env.PORT || 3000;
const server = http.createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "text/plain" });
  res.end("Hello from V-zone Express scaffold\\n");
});
server.listen(port, "127.0.0.1");
"""


def apps_qs(user: User) -> QuerySet[NodeApp]:
    qs = NodeApp.objects.select_related("owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def _assert_node_quota(owner: User) -> None:
    quota = getattr(owner, "quota", None)
    if quota is None:
        return
    limit = quota.node_apps
    if limit == 0 and owner.role == User.Role.ADMINISTRATOR:
        return
    used = NodeApp.objects.filter(owner=owner).count()
    if limit > 0 and used >= limit:
        raise QuotaExceeded(
            detail="Quota d'applications Node.js atteint.",
            extra={"limit": limit, "used": used},
        )


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_NODE_PROVISION_MODE", "auto").lower()
    return mode if mode in {"auto", "live", "mock"} else "auto"


def config_root() -> Path:
    root = Path(
        getattr(settings, "VZONE_NODE_CONFIG_DIR", None) or (Path(settings.VZONE_DATA_ROOT) / "node_apps")
    )
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
    base = int(getattr(settings, "VZONE_NODE_PORT_BASE", 9100))
    used = set(NodeApp.objects.filter(port__gt=0).values_list("port", flat=True))
    for offset in range(0, 5000):
        candidate = base + offset
        if candidate not in used:
            return candidate
    raise VZoneAPIException(detail="Aucun port disponible.", code="no_port", status_code=503)


def node_binary() -> str:
    configured = getattr(settings, "VZONE_NODE_BIN", "") or ""
    if configured:
        return configured
    return shutil.which("node") or "node"


def npm_binary() -> str:
    configured = getattr(settings, "VZONE_NPM_BIN", "") or ""
    if configured:
        return configured
    return shutil.which("npm") or "npm"


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
            detail="Échec commande Node.js.",
            code="node_cmd_failed",
            status_code=502,
            extra={"stderr": stderr, "cmd": cmd},
        ) from exc


def write_app_config(app: NodeApp) -> Path:
    root = config_root() / str(app.owner_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{app.name}.json"
    payload = {
        "id": app.pk,
        "owner": app.owner.username,
        "name": app.name,
        "framework": app.framework,
        "root": app.relative_root,
        "entrypoint": app.entrypoint,
        "start_script": app.start_script,
        "port": app.port,
        "node_version": app.node_version,
        "env": app.env_vars,
        "status": app.status,
        "pid": app.pid,
        "domain": app.domain_name,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _scaffold(app_root: Path, name: str, framework: str, entrypoint: str) -> None:
    app_root.mkdir(parents=True, exist_ok=True)
    (app_root / "logs").mkdir(exist_ok=True)
    pkg_path = app_root / "package.json"
    if not pkg_path.exists():
        pkg = {
            "name": name,
            "version": "1.0.0",
            "private": True,
            "main": entrypoint,
            "scripts": {
                "start": f"node {entrypoint}",
                "dev": f"node {entrypoint}",
            },
            "engines": {"node": ">=18"},
        }
        if framework == NodeApp.Framework.EXPRESS:
            pkg["dependencies"] = {"express": "^4.21.0"}
        elif framework == NodeApp.Framework.NEXT:
            pkg["scripts"] = {"start": "next start", "build": "next build", "dev": "next dev"}
            pkg["dependencies"] = {"next": "^14.2.0", "react": "^18.3.0", "react-dom": "^18.3.0"}
        elif framework == NodeApp.Framework.NEST:
            pkg["scripts"] = {"start": "node dist/main.js", "build": "echo build"}
        pkg_path.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")

    entry = app_root / entrypoint
    if not entry.exists():
        content = EXPRESS_SERVER if framework == NodeApp.Framework.EXPRESS else SERVER_JS
        entry.write_text(content, encoding="utf-8")

    readme = app_root / "README.vzone.md"
    if not readme.exists():
        readme.write_text(
            f"# Application Node.js V-zone\n\nFramework: {framework}\nEntrypoint: {entrypoint}\n",
            encoding="utf-8",
        )


@transaction.atomic
def create_node_app(
    *,
    owner: User,
    name: str,
    label: str = "",
    node_version: str = "20",
    framework: str = NodeApp.Framework.GENERIC,
    relative_root: str = "",
    start_script: str = "start",
    entrypoint: str = "server.js",
    domain_name: str = "",
    env_vars: dict | None = None,
    notes: str = "",
) -> NodeApp:
    slug = name.strip().lower().replace(" ", "-")
    if not NAME_RE.match(slug):
        raise VZoneAPIException(
            detail="Nom d'app invalide (a-z, 0-9, _-).",
            code="invalid_name",
            status_code=400,
        )
    if framework not in NodeApp.Framework.values:
        raise VZoneAPIException(detail="Framework invalide.", code="invalid_framework", status_code=400)
    _assert_node_quota(owner)
    if NodeApp.objects.filter(owner=owner, name=slug).exists():
        raise VZoneAPIException(detail="Cette application existe déjà.", code="exists", status_code=400)

    entry = (entrypoint or "server.js").strip() or "server.js"
    rel = relative_root.strip() or f"nodeapps/{slug}"
    rel, app_root = resolve_app_root(owner, rel)
    _scaffold(app_root, slug, framework, entry)

    app = NodeApp.objects.create(
        owner=owner,
        name=slug,
        label=label or slug,
        node_version=node_version,
        framework=framework,
        relative_root=rel,
        start_script=(start_script or "start").strip() or "start",
        entrypoint=entry,
        port=allocate_port(owner),
        env_vars=env_vars or {},
        domain_name=domain_name.strip().lower(),
        notes=notes,
        status=NodeApp.Status.STOPPED,
    )
    write_app_config(app)
    return app


@transaction.atomic
def update_node_app(
    app: NodeApp,
    *,
    label: str | None = None,
    start_script: str | None = None,
    entrypoint: str | None = None,
    domain_name: str | None = None,
    env_vars: dict | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
) -> NodeApp:
    if label is not None:
        app.label = label
    if start_script is not None:
        app.start_script = start_script
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


def npm_install(app: NodeApp) -> dict:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    pkg = app_root / "package.json"
    if not pkg.exists():
        raise VZoneAPIException(detail="package.json introuvable.", code="no_package", status_code=400)
    log = app_root / "logs" / "npm.log"
    if provision_mode() == "mock":
        log.write_text("mock npm install\n", encoding="utf-8")
        return {"mode": "mock", "package": str(pkg), "log": str(log)}
    result = _run([npm_binary(), "install"], cwd=app_root)
    log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    return {"mode": "live", "package": str(pkg), "log": str(log)}


@transaction.atomic
def start_node_app(app: NodeApp) -> NodeApp:
    if not app.is_active:
        raise VZoneAPIException(detail="Application désactivée.", code="inactive", status_code=400)
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    pid_file = app_root / "logs" / "app.pid"
    env = os.environ.copy()
    env["PORT"] = str(app.port)
    for key, value in (app.env_vars or {}).items():
        env[str(key)] = str(value)

    if provision_mode() == "mock":
        fake_pid = 20000 + (app.pk or 1)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(fake_pid), encoding="utf-8")
        app.pid = fake_pid
        app.status = NodeApp.Status.RUNNING
        app.last_error = ""
        app.last_started_at = timezone.now()
        app.save()
        write_app_config(app)
        return app

    cmd = [npm_binary(), "run", app.start_script]
    try:
        access = open(app_root / "logs" / "access.log", "a", encoding="utf-8")
        error = open(app_root / "logs" / "error.log", "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=str(app_root),
            env=env,
            stdout=access,
            stderr=error,
            start_new_session=True,
        )
        pid_file.write_text(str(proc.pid), encoding="utf-8")
        app.pid = proc.pid
        app.status = NodeApp.Status.RUNNING
        app.last_error = ""
        app.last_started_at = timezone.now()
    except Exception as exc:  # noqa: BLE001
        app.status = NodeApp.Status.ERROR
        app.last_error = str(exc)
        app.pid = None
        app.save()
        write_app_config(app)
        raise VZoneAPIException(
            detail="Impossible de démarrer l'application Node.js.",
            code="start_failed",
            status_code=502,
            extra={"error": str(exc)},
        ) from exc
    app.save()
    write_app_config(app)
    return app


@transaction.atomic
def stop_node_app(app: NodeApp) -> NodeApp:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    pid_file = app_root / "logs" / "app.pid"
    pid = app.pid
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = app.pid

    if provision_mode() != "mock" and pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            logger.info("Processus Node %s déjà arrêté", pid)

    if pid_file.exists():
        pid_file.unlink(missing_ok=True)
    app.pid = None
    app.status = NodeApp.Status.STOPPED
    app.last_error = ""
    app.save()
    write_app_config(app)
    return app


@transaction.atomic
def restart_node_app(app: NodeApp) -> NodeApp:
    stop_node_app(app)
    return start_node_app(app)


@transaction.atomic
def delete_node_app(app: NodeApp, *, remove_files: bool = False) -> None:
    if app.status == NodeApp.Status.RUNNING:
        stop_node_app(app)
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


def read_logs(app: NodeApp, *, lines: int = 100) -> dict:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    result = {}
    for name in ("error.log", "access.log", "npm.log"):
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
        "running": qs.filter(status=NodeApp.Status.RUNNING).count(),
        "stopped": qs.filter(status=NodeApp.Status.STOPPED).count(),
        "error": qs.filter(status=NodeApp.Status.ERROR).count(),
        "provision_mode": provision_mode(),
    }
