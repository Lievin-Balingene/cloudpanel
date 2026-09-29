"""Services Docker : create/run/stop/logs via CLI (ou mock)."""
from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.docker_mgmt.models import DockerContainer, DockerContainerLog
from apps.files.services import user_home

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,200}$", re.I)


def containers_qs(user: User) -> QuerySet[DockerContainer]:
    qs = DockerContainer.objects.select_related("owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_DOCKER_PROVISION_MODE", "auto").lower()
    return mode if mode in {"auto", "live", "mock"} else "auto"


def config_root() -> Path:
    root = Path(
        getattr(settings, "VZONE_DOCKER_CONFIG_DIR", None) or (Path(settings.VZONE_DATA_ROOT) / "docker")
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "meta").mkdir(exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    return root


def docker_binary() -> str:
    configured = getattr(settings, "VZONE_DOCKER_BIN", "") or ""
    if configured:
        return configured
    return shutil.which("docker") or "docker"


def docker_available() -> tuple[bool, str]:
    """Vérifie que le CLI Docker parle au démon (permission socket incluse)."""
    binary = docker_binary()
    if not shutil.which(binary) and not Path(binary).is_file():
        return False, (
            "Binaire Docker introuvable. Installez Docker "
            "(scripts/ensure-docker-access.sh) ou définissez VZONE_DOCKER_BIN."
        )
    try:
        proc = subprocess.run(
            [binary, "info"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        return False, (
            "Binaire Docker introuvable. Installez Docker "
            "ou définissez VZONE_DOCKER_BIN."
        )
    except subprocess.TimeoutExpired:
        return False, "Le démon Docker ne répond pas (timeout sur `docker info`)."
    if proc.returncode == 0:
        return True, ""
    hint = _humanize_docker_stderr((proc.stderr or proc.stdout or "").strip())
    return False, hint or "Docker indisponible (docker info a échoué)."


def _humanize_docker_stderr(stderr: str) -> str:
    lower = (stderr or "").lower()
    if not stderr:
        return "Échec commande Docker (sans détail)."
    if "permission denied" in lower and ("docker.sock" in lower or "connect" in lower):
        return (
            "Permission refusée sur le socket Docker. "
            "Ajoutez l'utilisateur API au groupe docker puis redémarrez : "
            "sudo bash /opt/vzone/scripts/ensure-docker-access.sh"
        )
    if (
        "cannot connect to the docker daemon" in lower
        or "is the docker daemon running" in lower
        or "connection refused" in lower
    ):
        return (
            "Le démon Docker n'est pas démarré ou inaccessible. "
            "Exécutez : sudo systemctl start docker "
            "puis sudo bash /opt/vzone/scripts/ensure-docker-access.sh"
        )
    if "port is already allocated" in lower or "address already in use" in lower:
        return f"Port hôte déjà utilisé. {stderr[:280]}"
    if "conflict" in lower or "is already in use by container" in lower:
        return f"Nom de conteneur déjà utilisé côté Docker. {stderr[:280]}"
    if "pull access denied" in lower or ("not found" in lower and "manifest" in lower):
        return f"Image introuvable ou accès refusé. {stderr[:280]}"
    if "no space left" in lower:
        return "Espace disque insuffisant pour Docker."
    return f"Échec commande Docker : {stderr[:400]}"


def _assert_docker_ready() -> None:
    """En mode live/auto : refuse tôt si Docker n'est pas utilisable."""
    if provision_mode() == "mock":
        return
    ok, hint = docker_available()
    if not ok:
        raise VZoneAPIException(
            detail=hint,
            code="docker_unavailable",
            status_code=503,
            extra={"hint": hint},
        )


def _assert_docker_quota(owner: User) -> None:
    quota = getattr(owner, "quota", None)
    limit = int(getattr(quota, "docker_containers", 0) or 0) if quota is not None else 0
    try:
        from apps.packages.models import PackageAssignment

        assignment = PackageAssignment.objects.filter(user=owner).select_related("package").first()
        if assignment and assignment.package is not None:
            limit = int(assignment.package.docker_containers or 0)
    except Exception:  # noqa: BLE001
        pass

    if limit == 0 and owner.role == User.Role.ADMINISTRATOR:
        return
    used = DockerContainer.objects.filter(owner=owner).exclude(status=DockerContainer.Status.REMOVED).count()
    if limit > 0 and used >= limit:
        raise QuotaExceeded(
            detail="Quota de conteneurs Docker atteint.",
            extra={"limit": limit, "used": used},
        )
    if limit == 0 and owner.role != User.Role.ADMINISTRATOR:
        raise QuotaExceeded(
            detail="Docker non inclus dans le package.",
            extra={"limit": 0, "used": used},
        )


def _sanitize_ports(owner: User, ports: dict | None) -> dict:
    """Interdit aux non-admins les ports host privilégiés (<1024) et ports panel."""
    cleaned: dict = {}
    reserved = {80, 443, 22, 25, 53, 3306, 5432, 8000, 9082, 9086, 9095}
    for host_port, container_port in (ports or {}).items():
        try:
            hp = int(str(host_port).split(":")[-1])
            cp = int(container_port)
        except (TypeError, ValueError) as exc:
            raise VZoneAPIException(
                detail=f"Port invalide: {host_port}:{container_port}",
                code="invalid_port",
                status_code=400,
            ) from exc
        if owner.role != User.Role.ADMINISTRATOR:
            if hp < 1024 or hp in reserved:
                raise VZoneAPIException(
                    detail=f"Port hôte {hp} réservé / privilégié.",
                    code="port_forbidden",
                    status_code=403,
                )
        cleaned[str(hp)] = cp
    return cleaned


def _ports_claimed_in_db(*, exclude_id: int | None = None) -> set[int]:
    used: set[int] = set()
    qs = DockerContainer.objects.exclude(status=DockerContainer.Status.REMOVED).only("id", "ports")
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    for row in qs.iterator():
        for key in (row.ports or {}):
            try:
                used.add(int(str(key).split(":")[-1]))
            except (TypeError, ValueError):
                continue
    return used


def _is_host_port_free(port: int, *, exclude_id: int | None = None) -> bool:
    """Vérifie qu'aucun process / conteneur panel n'utilise déjà ce port."""
    import socket

    if port in _ports_claimed_in_db(exclude_id=exclude_id):
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False


DOCKER_HOST_PORT_START = 12000
DOCKER_HOST_PORT_END = 18999


def allocate_host_port(
    *,
    preferred: int | None = None,
    start: int = DOCKER_HOST_PORT_START,
    end: int = DOCKER_HOST_PORT_END,
    exclude_id: int | None = None,
) -> int:
    """
    Alloue un port hôte libre pour un conteneur.
    Plage haute (12k–18k) pour laisser cohabiter beaucoup de conteneurs.
    """
    if preferred and preferred >= 1024 and _is_host_port_free(preferred, exclude_id=exclude_id):
        return preferred
    for port in range(start, end + 1):
        if _is_host_port_free(port, exclude_id=exclude_id):
            return port
    raise VZoneAPIException(
        detail=f"Aucun port hôte libre entre {start} et {end}.",
        code="no_free_port",
        status_code=503,
    )


def open_docker_host_ports(ports: dict | None) -> None:
    """
    Ouvre les ports hôte Docker dans UFW / iptables (accès public).
    Les images type nginx:alpine n'écoutent qu'en HTTP — pas de TLS sur ces ports.
    """
    if provision_mode() == "mock":
        return
    host_ports: list[int] = []
    for key in (ports or {}):
        try:
            host_ports.append(int(str(key).split(":")[-1]))
        except (TypeError, ValueError):
            continue
    for port in host_ports:
        if not (1 <= port <= 65535):
            continue
        try:
            if shutil.which("ufw"):
                subprocess.run(
                    ["ufw", "allow", f"{port}/tcp", "comment", f"vzone-docker-{port}"],
                    check=False,
                    capture_output=True,
                    timeout=15,
                )
            if shutil.which("firewall-cmd"):
                subprocess.run(
                    ["firewall-cmd", "--permanent", f"--add-port={port}/tcp"],
                    check=False,
                    capture_output=True,
                    timeout=15,
                )
                subprocess.run(
                    ["firewall-cmd", "--reload"],
                    check=False,
                    capture_output=True,
                    timeout=30,
                )
            if shutil.which("iptables"):
                check = subprocess.run(
                    ["iptables", "-C", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
                if check.returncode != 0:
                    subprocess.run(
                        ["iptables", "-I", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"],
                        check=False,
                        capture_output=True,
                        timeout=10,
                    )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Impossible d'ouvrir le port Docker %s: %s", port, exc)


def resolve_ports(
    owner: User,
    ports: dict | None,
    *,
    container_default: int = 80,
    exclude_id: int | None = None,
) -> dict:
    """
    Normalise le mapping ports pour multi-conteneurs :
    - vide → alloue un port hôte libre → container_default
    - port demandé occupé → réalloue un port libre (conserve le port conteneur)
    """
    cleaned = _sanitize_ports(owner, ports)
    if not cleaned:
        host = allocate_host_port(exclude_id=exclude_id)
        resolved = {str(host): container_default}
        open_docker_host_ports(resolved)
        return resolved

    resolved: dict[str, int] = {}
    for host_s, container_p in cleaned.items():
        host = int(host_s)
        if _is_host_port_free(host, exclude_id=exclude_id):
            resolved[str(host)] = int(container_p)
        else:
            free = allocate_host_port(exclude_id=exclude_id)
            resolved[str(free)] = int(container_p)
            logger.info(
                "Docker port %s occupé pour %s — réalloué %s→%s",
                host,
                owner.username,
                free,
                container_p,
            )
    open_docker_host_ports(resolved)
    return resolved


def _add_log(container: DockerContainer, event_type: str, *, success: bool = True, message: str = "") -> None:
    DockerContainerLog.objects.create(
        container=container,
        event_type=event_type,
        success=success,
        message=message[:4000],
    )


def write_meta(container: DockerContainer) -> Path:
    path = config_root() / "meta" / f"{container.owner_id}_{container.name}.json"
    path.write_text(
        json.dumps(
            {
                "id": container.pk,
                "owner": container.owner.username,
                "name": container.name,
                "image": container.image_ref,
                "container_id": container.container_id,
                "status": container.status,
                "ports": container.ports,
                "env": container.env_vars,
                "volumes": container.volumes,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _run_docker(args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess:
    cmd = [docker_binary(), *args]
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise VZoneAPIException(
            detail="Binaire Docker introuvable. Installez Docker ou définissez VZONE_DOCKER_BIN.",
            code="docker_not_found",
            status_code=503,
            extra={"stderr": str(exc), "cmd": cmd},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise VZoneAPIException(
            detail="Commande Docker expirée (pull d'image trop long ?).",
            code="docker_timeout",
            status_code=504,
            extra={"stderr": (exc.stderr or "") if isinstance(exc.stderr, str) else "", "cmd": cmd},
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or "").strip() or str(exc)
        raise VZoneAPIException(
            detail=_humanize_docker_stderr(stderr),
            code="docker_cmd_failed",
            status_code=502,
            extra={"stderr": stderr[:2000], "cmd": cmd, "returncode": exc.returncode},
        ) from exc


def _container_runtime_name(container: DockerContainer) -> str:
    return f"vz_{container.owner.username}_{container.name}"


def _cleanup_orphan_runtime(container: DockerContainer) -> None:
    """Supprime un conteneur Docker orphelin du même nom (échec précédent)."""
    if provision_mode() == "mock" or container.container_id:
        return
    name = _container_runtime_name(container)
    try:
        subprocess.run(
            [docker_binary(), "rm", "-f", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _pull_image(image_ref: str) -> None:
    """Pré-télécharge l'image (timeout long) pour des erreurs plus claires."""
    if provision_mode() == "mock":
        return
    _run_docker(["pull", image_ref], timeout=300)


def _resolve_volumes(owner: User, volumes: list) -> list[str]:
    home = user_home(owner)
    resolved: list[str] = []
    for item in volumes or []:
        raw = str(item)
        if ":" not in raw:
            raise VZoneAPIException(detail=f"Volume invalide: {raw}", code="invalid_volume", status_code=400)
        host_part, container_part = raw.split(":", 1)
        host_part = host_part.replace("\\", "/").strip("/")
        if ".." in Path(host_part).parts:
            raise VZoneAPIException(detail="Volume hors home.", code="invalid_volume", status_code=400)
        host_path = (home / host_part).resolve()
        try:
            host_path.relative_to(home)
        except ValueError as exc:
            raise VZoneAPIException(detail="Volume hors home.", code="path_forbidden", status_code=403) from exc
        host_path.mkdir(parents=True, exist_ok=True)
        resolved.append(f"{host_path}:{container_part}")
    return resolved


def _build_run_args(container: DockerContainer) -> list[str]:
    full_name = _container_runtime_name(container)
    args = [
        "run",
        "-d",
        "--name",
        full_name,
        "--restart",
        container.restart_policy,
        "--memory",
        f"{container.memory_mb}m",
        "--cpus",
        str(container.cpus),
        "--label",
        f"vzone.owner={container.owner.username}",
        "--label",
        f"vzone.name={container.name}",
    ]
    for host_port, container_port in (container.ports or {}).items():
        # Bind explicite 0.0.0.0 pour accès public (pas seulement localhost)
        args.extend(["-p", f"0.0.0.0:{host_port}:{container_port}"])
    for key, value in (container.env_vars or {}).items():
        args.extend(["-e", f"{key}={value}"])
    for vol in _resolve_volumes(container.owner, container.volumes or []):
        args.extend(["-v", vol])
    args.append(container.image_ref)
    if container.command:
        args.extend(container.command.split())
    return args


@transaction.atomic
def create_container(
    *,
    owner: User,
    name: str,
    image: str,
    tag: str = "latest",
    ports: dict | None = None,
    env_vars: dict | None = None,
    volumes: list | None = None,
    command: str = "",
    restart_policy: str = DockerContainer.RestartPolicy.UNLESS_STOPPED,
    memory_mb: int = 512,
    cpus: Decimal | float = 1,
    label: str = "",
    notes: str = "",
    start_now: bool = True,
) -> DockerContainer:
    _assert_docker_quota(owner)
    ports = resolve_ports(owner, ports)
    slug = name.strip().lower().replace(" ", "-")
    if not NAME_RE.match(slug):
        raise VZoneAPIException(detail="Nom de conteneur invalide.", code="invalid_name", status_code=400)
    img = image.strip()
    if not IMAGE_RE.match(img):
        raise VZoneAPIException(detail="Image Docker invalide.", code="invalid_image", status_code=400)
    if DockerContainer.objects.filter(owner=owner, name=slug).exclude(status=DockerContainer.Status.REMOVED).exists():
        raise VZoneAPIException(detail="Ce conteneur existe déjà.", code="exists", status_code=400)
    if restart_policy not in DockerContainer.RestartPolicy.values:
        raise VZoneAPIException(detail="Restart policy invalide.", code="invalid_restart", status_code=400)

    container = DockerContainer.objects.create(
        owner=owner,
        name=slug,
        label=label or slug,
        image=img,
        tag=(tag or "latest").strip() or "latest",
        ports=ports or {},
        env_vars=env_vars or {},
        volumes=volumes or [],
        command=command.strip(),
        restart_policy=restart_policy,
        memory_mb=max(64, int(memory_mb)),
        cpus=Decimal(str(cpus)),
        notes=notes,
        status=DockerContainer.Status.CREATED,
    )
    write_meta(container)
    _add_log(container, DockerContainerLog.Event.CREATE, message=f"created {container.image_ref}")
    if start_now:
        start_container(container)
    return container


def start_container(container: DockerContainer) -> DockerContainer:
    if not container.is_active:
        raise VZoneAPIException(detail="Conteneur désactivé.", code="inactive", status_code=400)

    try:
        if provision_mode() == "mock":
            container.container_id = secrets.token_hex(16)
            container.status = DockerContainer.Status.RUNNING
            container.last_error = ""
            container.last_started_at = timezone.now()
            container.save()
            log_path = config_root() / "logs" / f"{container.owner_id}_{container.name}.log"
            log_path.write_text(f"mock start {container.image_ref}\n", encoding="utf-8")
            message = f"mock started {container.container_id[:12]}"
        else:
            _assert_docker_ready()
            if container.container_id:
                _run_docker(["start", container.container_id])
                cid = container.container_id
            else:
                _pull_image(container.image_ref)
                _cleanup_orphan_runtime(container)
                try:
                    result = _run_docker(_build_run_args(container), timeout=180)
                except VZoneAPIException as exc:
                    detail = str(exc.detail).lower()
                    port_busy = "port" in detail and (
                        "already" in detail or "utilisé" in detail or "allocated" in detail
                    )
                    if not port_busy:
                        raise
                    # Course critique : réallouer un port hôte libre et retenter une fois
                    old_cp = 80
                    if container.ports:
                        try:
                            old_cp = int(next(iter(container.ports.values())))
                        except (TypeError, ValueError, StopIteration):
                            old_cp = 80
                    free = allocate_host_port(exclude_id=container.pk)
                    container.ports = {str(free): old_cp}
                    container.save(update_fields=["ports", "updated_at"])
                    open_docker_host_ports(container.ports)
                    write_meta(container)
                    logger.warning(
                        "Docker port conflict for %s — retry on %s→%s",
                        container.name,
                        free,
                        old_cp,
                    )
                    result = _run_docker(_build_run_args(container), timeout=180)
                cid = (result.stdout or "").strip()
                if not cid:
                    raise VZoneAPIException(
                        detail="Docker n'a pas renvoyé d'identifiant de conteneur.",
                        code="docker_empty_id",
                        status_code=502,
                    )
                container.container_id = cid
            container.status = DockerContainer.Status.RUNNING
            container.last_error = ""
            container.last_started_at = timezone.now()
            container.save()
            message = f"started {cid[:12]}"
        write_meta(container)
        _add_log(container, DockerContainerLog.Event.START, message=message)
    except VZoneAPIException as exc:
        container.status = DockerContainer.Status.ERROR
        container.last_error = str(exc.detail)
        container.save(update_fields=["status", "last_error", "updated_at"])
        _add_log(container, DockerContainerLog.Event.START, success=False, message=str(exc.detail))
        raise
    return container


def stop_container(container: DockerContainer) -> DockerContainer:
    try:
        if provision_mode() == "mock":
            container.status = DockerContainer.Status.STOPPED
            container.save(update_fields=["status", "updated_at"])
            message = "mock stopped"
        else:
            if container.container_id:
                _run_docker(["stop", container.container_id])
            container.status = DockerContainer.Status.STOPPED
            container.save(update_fields=["status", "updated_at"])
            message = f"stopped {container.container_id[:12] if container.container_id else ''}"
        write_meta(container)
        _add_log(container, DockerContainerLog.Event.STOP, message=message)
    except VZoneAPIException as exc:
        container.status = DockerContainer.Status.ERROR
        container.last_error = str(exc.detail)
        container.save(update_fields=["status", "last_error", "updated_at"])
        _add_log(container, DockerContainerLog.Event.STOP, success=False, message=str(exc.detail))
        raise
    return container


def restart_container(container: DockerContainer) -> DockerContainer:
    if container.status == DockerContainer.Status.RUNNING:
        stop_container(container)
    container = start_container(container)
    _add_log(container, DockerContainerLog.Event.RESTART, message="restarted")
    return container


@transaction.atomic
def remove_container(container: DockerContainer, *, force: bool = True) -> None:
    try:
        if provision_mode() != "mock" and container.container_id:
            args = ["rm"]
            if force:
                args.append("-f")
            args.append(container.container_id)
            try:
                _run_docker(args)
            except VZoneAPIException:
                logger.warning("Impossible de supprimer le conteneur Docker %s", container.container_id)
        meta = config_root() / "meta" / f"{container.owner_id}_{container.name}.json"
        if meta.exists():
            meta.unlink(missing_ok=True)
        _add_log(container, DockerContainerLog.Event.REMOVE, message="removed")
        container.delete()
    except VZoneAPIException as exc:
        _add_log(container, DockerContainerLog.Event.REMOVE, success=False, message=str(exc.detail))
        raise


def read_container_logs(container: DockerContainer, *, tail: int = 100) -> str:
    tail = max(1, min(tail, 2000))
    if provision_mode() == "mock":
        path = config_root() / "logs" / f"{container.owner_id}_{container.name}.log"
        if path.exists():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-tail:])
        return "mock: no logs yet"
    if not container.container_id:
        return ""
    result = _run_docker(["logs", "--tail", str(tail), container.container_id])
    _add_log(container, DockerContainerLog.Event.LOGS, message=f"tail={tail}")
    return (result.stdout or "") + (result.stderr or "")


@transaction.atomic
def update_container(
    container: DockerContainer,
    *,
    label: str | None = None,
    env_vars: dict | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
    memory_mb: int | None = None,
    restart_policy: str | None = None,
) -> DockerContainer:
    if label is not None:
        container.label = label
    if env_vars is not None:
        container.env_vars = env_vars
    if notes is not None:
        container.notes = notes
    if is_active is not None:
        container.is_active = is_active
    if memory_mb is not None:
        container.memory_mb = max(64, int(memory_mb))
    if restart_policy is not None:
        if restart_policy not in DockerContainer.RestartPolicy.values:
            raise VZoneAPIException(detail="Restart policy invalide.", code="invalid_restart", status_code=400)
        container.restart_policy = restart_policy
    container.save()
    write_meta(container)
    return container


def overview_for(user: User) -> dict:
    from apps.docker_mgmt.build_compose import overview_build_compose

    qs = containers_qs(user).exclude(status=DockerContainer.Status.REMOVED)
    available, availability_hint = (True, "")
    if provision_mode() != "mock":
        available, availability_hint = docker_available()
    data = {
        "containers": qs.count(),
        "running": qs.filter(status=DockerContainer.Status.RUNNING).count(),
        "stopped": qs.filter(status=DockerContainer.Status.STOPPED).count(),
        "error": qs.filter(status=DockerContainer.Status.ERROR).count(),
        "provision_mode": provision_mode(),
        "docker_available": available,
        "docker_hint": availability_hint,
    }
    data.update(overview_build_compose(user))
    return data
