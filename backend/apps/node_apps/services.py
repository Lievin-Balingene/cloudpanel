"""Services applications Node.js : scaffold, npm, start/stop, logs."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.core.app_runtime import (
    free_listen_port,
    kill_app_pid,
    normalize_app_domain,
    our_process_owns_port,
    pids_listening_on_port,
    wait_port,
)
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.files.services import user_home
from apps.node_apps.models import NodeApp
from apps.security.runas import build_runas_cmd

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")

SERVER_JS = """\
const http = require("http");
const port = Number(process.env.PORT) || 3000;
const server = http.createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({ ok: true, panel: "vzone", path: req.url || "/" }));
});
server.listen(port, "127.0.0.1", () => {
  console.log(`V-zone Node app listening on 127.0.0.1:${port}`);
});
"""

EXPRESS_SERVER = """\
const express = require("express");
const app = express();
const port = Number(process.env.PORT) || 3000;

app.get("/", (_req, res) => {
  res.json({ ok: true, panel: "vzone", framework: "express" });
});

app.get("/health", (_req, res) => {
  res.type("text").send("ok");
});

app.listen(port, "127.0.0.1", () => {
  console.log(`V-zone Express listening on 127.0.0.1:${port}`);
});
"""


def _refresh_domain_routing(domain_name: str = "") -> None:
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
            for d in domains:
                try:
                    sync_domain_vhost(d)
                except Exception:  # noqa: BLE001
                    logger.debug("sync_domain_vhost node skip", exc_info=True)
        from apps.domains.services import refresh_web_routing

        refresh_web_routing()
    except Exception:  # noqa: BLE001
        logger.debug("refresh_web_routing node skip", exc_info=True)


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
    # Éviter aussi les ports Python
    try:
        from apps.python_apps.models import PythonApp

        used |= set(PythonApp.objects.filter(port__gt=0).values_list("port", flat=True))
    except Exception:  # noqa: BLE001
        pass
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


def _is_hello_scaffold(text: str) -> bool:
    low = (text or "").lower()
    return "hello from v-zone" in low


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
            pkg["scripts"] = {"start": "next start -H 127.0.0.1 -p $PORT", "build": "next build", "dev": "next dev"}
            pkg["dependencies"] = {"next": "^14.2.0", "react": "^18.3.0", "react-dom": "^18.3.0"}
        elif framework == NodeApp.Framework.NEST:
            pkg["scripts"] = {"start": "node dist/main.js", "build": "echo build"}
        pkg_path.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")

    entry = app_root / entrypoint
    content = EXPRESS_SERVER if framework == NodeApp.Framework.EXPRESS else SERVER_JS
    if not entry.exists():
        entry.write_text(content, encoding="utf-8")
    else:
        try:
            existing = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            existing = ""
        if _is_hello_scaffold(existing):
            try:
                entry.with_suffix(entry.suffix + ".bak").write_text(existing, encoding="utf-8")
            except OSError:
                pass
            entry.write_text(content, encoding="utf-8")

    readme = app_root / "README.vzone.md"
    if not readme.exists():
        readme.write_text(
            "# Application Node.js V-zone\n\n"
            f"Framework: {framework}\nEntrypoint: {entrypoint}\n\n"
            "1. Déposez votre code dans ce dossier\n"
            "2. npm install (bouton Installer)\n"
            "3. Démarrez l'app — le domaine proxifie vers PORT\n",
            encoding="utf-8",
        )


def _claim_node_domain(app: NodeApp, domain_name: str) -> None:
    name = normalize_app_domain(domain_name)
    if not name:
        return
    NodeApp.objects.filter(domain_name__iexact=name).exclude(pk=app.pk).update(domain_name="")
    NodeApp.objects.filter(domain_name__iexact=f"www.{name}").exclude(pk=app.pk).update(domain_name="")
    try:
        from apps.python_apps.models import PythonApp

        PythonApp.objects.filter(domain_name__iexact=name).update(domain_name="")
        PythonApp.objects.filter(domain_name__iexact=f"www.{name}").update(domain_name="")
    except Exception:  # noqa: BLE001
        pass


def _fix_client_paths(owner: User, *paths: Path) -> None:
    try:
        from apps.python_apps.services import fix_client_paths

        fix_client_paths(owner, *paths, required=False)
    except Exception:  # noqa: BLE001
        logger.debug("fix_client_paths node skip", exc_info=True)


def _prepare_node_logs(owner: User, app_root: Path) -> tuple[Path, Path]:
    logs = app_root / "logs"
    access_log = logs / "access.log"
    error_log = logs / "error.log"
    try:
        logs.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("mkdir node logs %s: %s", logs, exc)
    for path in (access_log, error_log):
        if not path.exists():
            try:
                path.touch()
            except OSError:
                pass
        try:
            path.chmod(0o666)
        except OSError:
            pass
    _fix_client_paths(owner, logs, access_log, error_log, app_root)
    return access_log, error_log


def _tail_log(path: Path, *, max_chars: int = 1500) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-max_chars:] if len(text) > max_chars else text


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
    _fix_client_paths(owner, app_root)

    domain = normalize_app_domain(domain_name)
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
        domain_name=domain,
        notes=notes,
        status=NodeApp.Status.STOPPED,
    )
    if domain:
        _claim_node_domain(app, domain)
        app.domain_name = domain
        app.save(update_fields=["domain_name", "updated_at"])
    write_app_config(app)
    _refresh_domain_routing(app.domain_name)
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
        app.domain_name = normalize_app_domain(domain_name)
        if app.domain_name:
            _claim_node_domain(app, app.domain_name)
    if env_vars is not None:
        app.env_vars = env_vars
    if notes is not None:
        app.notes = notes
    if is_active is not None:
        app.is_active = is_active
    app.save()
    write_app_config(app)
    _refresh_domain_routing(app.domain_name)
    return app


def npm_install(app: NodeApp) -> dict:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    pkg = app_root / "package.json"
    if not pkg.exists():
        raise VZoneAPIException(detail="package.json introuvable.", code="no_package", status_code=400)
    log = app_root / "logs" / "npm.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    if provision_mode() == "mock":
        log.write_text("mock npm install\n", encoding="utf-8")
        return {"mode": "mock", "package": str(pkg), "log": str(log)}
    env = os.environ.copy()
    # Isoler un peu le PATH npm
    result = _run([npm_binary(), "install", "--omit=dev"], cwd=app_root, env=env)
    log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    _fix_client_paths(app.owner, app_root, app_root / "node_modules")
    return {"mode": "live", "package": str(pkg), "log": str(log)}


def _ensure_node_modules(app: NodeApp, app_root: Path) -> None:
    """npm install si node_modules absent (Express / deps package.json)."""
    pkg = app_root / "package.json"
    modules = app_root / "node_modules"
    if not pkg.exists() or modules.is_dir():
        return
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    if not deps:
        return
    logger.info("npm install auto pour %s (node_modules manquant)", app.name)
    npm_install(app)


def _build_start_command(app: NodeApp, app_root: Path) -> list[str]:
    """Préfère `npm run <script>` ; fallback `node <entrypoint>`."""
    pkg = app_root / "package.json"
    script = (app.start_script or "start").strip() or "start"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts") or {}
            if script in scripts:
                return [npm_binary(), "run", script]
        except (OSError, json.JSONDecodeError):
            pass
    entry = (app.entrypoint or "server.js").strip() or "server.js"
    return [node_binary(), entry]


@transaction.atomic
def start_node_app(app: NodeApp) -> NodeApp:
    if not app.is_active:
        raise VZoneAPIException(detail="Application désactivée.", code="inactive", status_code=400)
    if app.last_error:
        app.last_error = ""
        app.save(update_fields=["last_error", "updated_at"])

    _, app_root = resolve_app_root(app.owner, app.relative_root)
    # Remplacer stub Hello Express si encore présent
    entry_path = app_root / (app.entrypoint or "server.js")
    if entry_path.is_file():
        try:
            if _is_hello_scaffold(entry_path.read_text(encoding="utf-8", errors="replace")):
                _scaffold(app_root, app.name, app.framework, app.entrypoint or "server.js")
        except OSError:
            pass

    access_log, error_log = _prepare_node_logs(app.owner, app_root)
    pid_file = app_root / "logs" / "app.pid"
    env = os.environ.copy()
    env["PORT"] = str(app.port)
    env["HOST"] = "127.0.0.1"
    env["NODE_ENV"] = env.get("NODE_ENV") or "production"
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
        _refresh_domain_routing(app.domain_name)
        return app

    # Stop précédent + libérer le port (node orphelin)
    if app.pid or pid_file.exists():
        try:
            stop_node_app(app)
            app.refresh_from_db()
        except Exception:  # noqa: BLE001
            logger.debug("stop node avant start ignoré", exc_info=True)
    free_listen_port(app.port)

    try:
        _ensure_node_modules(app, app_root)
    except VZoneAPIException as exc:
        app.status = NodeApp.Status.ERROR
        app.last_error = str(exc.detail)
        app.save()
        write_app_config(app)
        raise

    cmd = _build_start_command(app, app_root)
    try:
        from apps.accounts.linux_users import jail_username_for

        access_f = open(access_log, "a", encoding="utf-8")  # noqa: SIM115
        error_f = open(error_log, "a", encoding="utf-8")  # noqa: SIM115
        jail = jail_username_for(app.owner)
        spawn_cmd = build_runas_cmd(jail, cmd, env=env)
        proc = subprocess.Popen(
            spawn_cmd,
            cwd=str(app_root),
            stdout=access_f,
            stderr=error_f,
            start_new_session=True,
        )
        if not wait_port(app.port, timeout_s=20.0):
            err = _tail_log(error_log)
            kill_app_pid(proc.pid)
            free_listen_port(app.port)
            raise RuntimeError(
                f"Le port {app.port} n'écoute pas après démarrage Node. "
                + (err[-500:] if err else f"Commande: {' '.join(cmd)}")
            )
        if proc.poll() is not None:
            err = _tail_log(error_log)
            holders = pids_listening_on_port(app.port)
            free_listen_port(app.port)
            hint = ""
            if "EADDRINUSE" in err or "address already in use" in err.lower():
                hint = f" Port {app.port} déjà pris (pids {holders})."
            raise RuntimeError(
                (err[-600:] if err else f"Process Node arrêté (code {proc.returncode}).") + hint
            )
        if not our_process_owns_port(proc.pid, app.port):
            holders = pids_listening_on_port(app.port)
            kill_app_pid(proc.pid)
            free_listen_port(app.port)
            raise RuntimeError(
                f"Port {app.port} occupé par un autre process {holders or '(inconnu)'}. "
                f"sudo vzone-kill-port {app.port} puis Restart."
            )
        try:
            pid_file.write_text(str(proc.pid), encoding="utf-8")
        except OSError:
            _fix_client_paths(app.owner, pid_file.parent)
            pid_file.write_text(str(proc.pid), encoding="utf-8")
        app.pid = proc.pid
        app.status = NodeApp.Status.RUNNING
        app.last_error = ""
        app.last_started_at = timezone.now()
    except Exception as exc:  # noqa: BLE001
        detail = str(exc.detail) if isinstance(exc, VZoneAPIException) else str(exc)
        err_tail = _tail_log(error_log)
        if err_tail and err_tail not in detail:
            detail = f"{detail}\n{err_tail[-400:]}"
        detail = detail.strip()[:900] or "Échec démarrage Node.js."
        app.status = NodeApp.Status.ERROR
        app.last_error = detail
        app.pid = None
        app.save()
        write_app_config(app)
        raise VZoneAPIException(
            detail=f"Impossible de démarrer l'application Node.js : {detail[:520]}",
            code="start_failed",
            status_code=502,
            extra={"error": detail, "port": app.port},
        ) from exc
    app.save()
    write_app_config(app)
    _refresh_domain_routing(app.domain_name)
    return app


@transaction.atomic
def stop_node_app(app: NodeApp) -> NodeApp:
    _, app_root = resolve_app_root(app.owner, app.relative_root)
    pid_file = app_root / "logs" / "app.pid"
    pid = app.pid
    try:
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
            except ValueError:
                pid = app.pid
    except OSError as exc:
        logger.warning("lecture pid Node %s: %s", pid_file, exc)

    if provision_mode() != "mock":
        if pid:
            kill_app_pid(pid)
        if app.port:
            free_listen_port(app.port)

    _clear_node_pid_file(app.owner, pid_file)
    app.pid = None
    app.status = NodeApp.Status.STOPPED
    app.last_error = ""
    app.save()
    write_app_config(app)
    _refresh_domain_routing(app.domain_name)
    return app


def _clear_node_pid_file(owner: User, pid_file: Path) -> None:
    """Supprime app.pid même si owned par le jail (évite HTTP 500 au stop)."""
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
            logger.warning("unlink pid Node %s: %s", pid_file, exc)
            return False

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
        logger.warning("runas rm pid Node %s échoué", pid_file, exc_info=True)

    _try_unlink()


@transaction.atomic
def restart_node_app(app: NodeApp) -> NodeApp:
    stop_node_app(app)
    return start_node_app(app)


@transaction.atomic
def delete_node_app(app: NodeApp, *, remove_files: bool = False) -> None:
    domain = app.domain_name
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
    _refresh_domain_routing(domain)


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
    home = ""
    try:
        home = str(user_home(user))
    except Exception:  # noqa: BLE001
        home = ""
    return {
        "apps": qs.count(),
        "running": qs.filter(status=NodeApp.Status.RUNNING).count(),
        "stopped": qs.filter(status=NodeApp.Status.STOPPED).count(),
        "error": qs.filter(status=NodeApp.Status.ERROR).count(),
        "provision_mode": provision_mode(),
        "home_path": home,
    }
