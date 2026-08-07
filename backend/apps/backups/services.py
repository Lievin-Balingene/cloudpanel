"""Service layer backups — Restic + Rclone (async via Celery)."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.backups.models import (
    BackupArchive,
    BackupDestination,
    BackupEventLog,
    BackupSchedule,
)
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.core.models import AuditLog
from apps.databases.crypto import decrypt_secret, encrypt_secret
from apps.files.services import ensure_cpanel_tree, personal_home

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,47}$")
VALID_INCLUDES = frozenset({"home", "databases", "email"})
MAX_BACKUPS_DEFAULT = 10


# ---------------------------------------------------------------------------
# Querysets / mode
# ---------------------------------------------------------------------------


def archives_qs(user: User) -> QuerySet[BackupArchive]:
    qs = BackupArchive.objects.select_related("owner", "destination")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def schedules_qs(user: User) -> QuerySet[BackupSchedule]:
    qs = BackupSchedule.objects.select_related("owner", "destination")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def destinations_qs(user: User) -> QuerySet[BackupDestination]:
    qs = BackupDestination.objects.all()
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner__isnull=True) | Q(owner=user) | Q(owner__parent=user))
    return qs.filter(Q(owner__isnull=True) | Q(owner=user))


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_BACKUP_PROVISION_MODE", "auto").lower()
    if mode not in {"auto", "live", "mock"}:
        mode = "auto"
    if mode == "auto":
        from shutil import which

        if which(str(getattr(settings, "VZONE_RESTIC_BIN", "restic") or "restic")):
            return "live"
        home_root = Path(getattr(settings, "VZONE_HOME_ROOT", "/home"))
        return "live" if home_root.exists() else "mock"
    return mode


def config_root() -> Path:
    root = Path(
        getattr(settings, "VZONE_BACKUP_DIR", None) or (Path(settings.VZONE_DATA_ROOT) / "backups")
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "archives").mkdir(exist_ok=True)
    (root / "meta").mkdir(exist_ok=True)
    (root / "staging").mkdir(exist_ok=True)
    (root / "restic").mkdir(exist_ok=True)
    (root / "cache").mkdir(exist_ok=True)
    return root


def _account_home(owner: User) -> Path:
    return personal_home(owner)


def _add_log(
    owner: User,
    event_type: str,
    *,
    archive: BackupArchive | None = None,
    success: bool = True,
    message: str = "",
) -> None:
    BackupEventLog.objects.create(
        owner=owner,
        archive=archive,
        event_type=event_type,
        success=success,
        message=message[:4000],
    )


def _assert_backup_feature(owner: User) -> None:
    try:
        assignment = owner.package_assignment
    except Exception:  # RelatedObjectDoesNotExist
        assignment = None
    if assignment and assignment.package and not assignment.package.allow_backup:
        raise VZoneAPIException(
            detail="Les sauvegardes ne sont pas autorisées sur ce package.",
            code="backup_disabled",
            status_code=403,
        )


def _assert_backup_allowed(owner: User) -> None:
    _assert_backup_feature(owner)
    limit = int(getattr(settings, "VZONE_BACKUP_MAX", MAX_BACKUPS_DEFAULT))
    if owner.role == User.Role.ADMINISTRATOR and limit == 0:
        return
    used = BackupArchive.objects.filter(owner=owner).exclude(
        status__in={BackupArchive.Status.FAILED}
    ).count()
    if limit > 0 and used >= limit:
        raise QuotaExceeded(
            detail="Quota de sauvegardes atteint.",
            extra={"limit": limit, "used": used},
        )


def _normalize_includes(includes: list | None, backup_type: str) -> list[str]:
    if backup_type in {
        BackupArchive.BackupType.FULL,
        BackupArchive.BackupType.INCREMENTAL,
    }:
        return ["home", "databases", "email"]
    if backup_type == BackupArchive.BackupType.HOME:
        return ["home"]
    if backup_type == BackupArchive.BackupType.DATABASES:
        return ["databases"]
    if backup_type == BackupArchive.BackupType.EMAIL:
        return ["email"]
    items = [str(x).strip().lower() for x in (includes or []) if str(x).strip()]
    items = [x for x in items if x in VALID_INCLUDES]
    if not items:
        raise VZoneAPIException(
            detail="Aucun composant valide à sauvegarder.",
            code="invalid_includes",
            status_code=400,
        )
    return items


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------


def _encrypt_json(data: dict) -> str:
    return encrypt_secret(json.dumps(data))


def _decrypt_json(blob: str) -> dict:
    if not blob:
        return {}
    try:
        return json.loads(decrypt_secret(blob))
    except Exception:  # noqa: BLE001
        return {}


def resolve_destination(
    owner: User,
    destination_id: int | None = None,
) -> BackupDestination:
    if destination_id:
        dest = destinations_qs(owner).filter(pk=destination_id, is_active=True).first()
        if not dest:
            raise VZoneAPIException(
                detail="Destination introuvable.",
                code="destination_not_found",
                status_code=404,
            )
        return dest
    dest = (
        destinations_qs(owner)
        .filter(is_active=True, is_default=True)
        .order_by("-owner_id")
        .first()
    )
    if dest:
        return dest
    # Auto-créer destination locale par défaut
    return ensure_local_destination(owner)


def ensure_local_destination(owner: User | None = None) -> BackupDestination:
    """Destination locale chiffrée Restic (créée à la demande)."""
    from apps.backups.engine.restic import generate_password

    name = "local-default"
    existing = BackupDestination.objects.filter(owner=owner, name=name).first()
    if existing:
        return existing
    password = generate_password()
    local_path = config_root() / "restic" / ("global" if owner is None else str(owner.pk))
    local_path.mkdir(parents=True, exist_ok=True)
    dest = BackupDestination.objects.create(
        owner=owner,
        name=name,
        label="Stockage local (Restic)",
        provider=BackupDestination.Provider.LOCAL,
        config={"path": str(local_path)},
        restic_password_secret=encrypt_secret(password),
        credentials_secret="",
        rclone_remote="",
        repository_uri=str(local_path),
        is_default=True,
        is_active=True,
    )
    return dest


@transaction.atomic
def create_destination(
    *,
    actor: User,
    name: str,
    provider: str,
    config: dict | None = None,
    credentials: dict | None = None,
    label: str = "",
    restic_password: str = "",
    is_default: bool = False,
    owner: User | None = None,
) -> BackupDestination:
    from apps.backups.engine import rclone as rclone_mod
    from apps.backups.engine.restic import generate_password, init_repository

    if actor.role not in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
        # Clients : destinations personnelles uniquement
        owner = actor
    elif owner is None and actor.role != User.Role.ADMINISTRATOR:
        owner = actor

    slug = (name or "").strip().lower().replace(" ", "-")
    if not NAME_RE.match(slug):
        raise VZoneAPIException(detail="Nom de destination invalide.", code="invalid_name", status_code=400)
    if provider not in BackupDestination.Provider.values:
        raise VZoneAPIException(detail="Provider invalide.", code="invalid_provider", status_code=400)
    if BackupDestination.objects.filter(owner=owner, name=slug).exists():
        raise VZoneAPIException(detail="Destination déjà existante.", code="exists", status_code=400)

    cfg = dict(config or {})
    creds = dict(credentials or {})
    password = (restic_password or "").strip() or generate_password()
    remote = f"vz{secrets.token_hex(4)}"
    local_fallback = config_root() / "restic" / ("global" if owner is None else str(owner.pk)) / slug

    dest = BackupDestination(
        owner=owner,
        name=slug,
        label=label or slug,
        provider=provider,
        config=cfg,
        restic_password_secret=encrypt_secret(password),
        credentials_secret=_encrypt_json(creds) if creds else "",
        rclone_remote=remote if provider != BackupDestination.Provider.LOCAL else "",
        is_default=is_default,
        is_active=True,
    )
    dest.repository_uri = rclone_mod.repository_uri(
        provider=provider,
        remote_name=remote,
        config=cfg,
        local_fallback=local_fallback,
    )
    dest.save()

    if is_default:
        BackupDestination.objects.filter(owner=owner, is_default=True).exclude(pk=dest.pk).update(
            is_default=False
        )

    if provision_mode() != "mock" and provider != BackupDestination.Provider.LOCAL:
        from apps.backups.engine.providers import provider_path

        conf_path = rclone_mod.write_rclone_config(
            destination_id=dest.pk,
            remote_name=remote,
            provider=provider,
            config=cfg,
            credentials=creds,
        )
        ok, msg = rclone_mod.test_remote(conf_path, remote, provider_path(provider, cfg))
        if not ok:
            dest.last_error = msg[:2000]
            dest.save(update_fields=["last_error", "updated_at"])

    if provision_mode() != "mock":
        rclone_cfg = None
        if provider != BackupDestination.Provider.LOCAL:
            from apps.backups.engine.rclone import config_path_for

            rclone_cfg = config_path_for(dest.pk)
        result = init_repository(
            repository=dest.repository_uri,
            password=password,
            rclone_config=rclone_cfg if rclone_cfg and rclone_cfg.is_file() else None,
        )
        if not result.ok:
            dest.last_error = result.output[:2000]
            dest.save(update_fields=["last_error", "updated_at"])
            raise VZoneAPIException(
                detail="Impossible d'initialiser le dépôt Restic.",
                code="restic_init_failed",
                status_code=502,
                extra={"error": result.output[:500]},
            )

    _add_log(
        owner or actor,
        BackupEventLog.Event.DESTINATION,
        message=f"created destination {slug} ({provider})",
    )
    return dest


def delete_destination(dest: BackupDestination) -> None:
    from apps.backups.engine.rclone import config_path_for

    conf = config_path_for(dest.pk)
    conf.unlink(missing_ok=True)
    owner = dest.owner
    name = dest.name
    dest.delete()
    if owner:
        _add_log(owner, BackupEventLog.Event.DESTINATION, message=f"deleted {name}")


def destination_credentials(dest: BackupDestination) -> tuple[str, dict, Path | None]:
    """Retourne (restic_password, credentials, rclone_config_path)."""
    from apps.backups.engine.rclone import config_path_for, write_rclone_config

    raw = decrypt_secret(dest.restic_password_secret) if dest.restic_password_secret else None
    password = raw or ""
    creds = _decrypt_json(dest.credentials_secret)
    conf_path = None
    if dest.provider != BackupDestination.Provider.LOCAL:
        conf_path = config_path_for(dest.pk)
        if not conf_path.is_file():
            write_rclone_config(
                destination_id=dest.pk,
                remote_name=dest.rclone_remote or f"vz{dest.pk}",
                provider=dest.provider,
                config=dest.config or {},
                credentials=creds,
            )
    return password, creds, conf_path


# ---------------------------------------------------------------------------
# Staging sources
# ---------------------------------------------------------------------------


def _staging_dir(archive: BackupArchive) -> Path:
    path = config_root() / "staging" / str(archive.owner_id) / archive.name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _prepare_sources(archive: BackupArchive) -> list[Path]:
    """Prépare un arbre staging (home + dumps DB/email) pour Restic."""
    staging = _staging_dir(archive)
    # Nettoyer staging précédent
    for child in staging.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)

    paths: list[Path] = []
    includes = archive.includes or []

    if "home" in includes:
        home = _account_home(archive.owner)
        home.mkdir(parents=True, exist_ok=True)
        link = staging / "home"
        if link.exists() or link.is_symlink():
            if link.is_symlink() or link.is_file():
                link.unlink(missing_ok=True)
            else:
                shutil.rmtree(link, ignore_errors=True)
        try:
            link.symlink_to(home, target_is_directory=True)
        except OSError:
            # Windows / FS sans symlink → copie légère marqueur
            link.mkdir(parents=True, exist_ok=True)
            (link / ".vzone-home-path").write_text(str(home), encoding="utf-8")
            # En live on backup le home réel directement
            paths.append(home)
        else:
            paths.append(link)

    if "databases" in includes:
        db_dir = staging / "databases"
        db_dir.mkdir(parents=True, exist_ok=True)
        (db_dir / "README.txt").write_text(
            "Database dumps — intégration mysqldump/pg_dump selon stack.\n",
            encoding="utf-8",
        )
        try:
            from apps.databases.models import Database

            for db in Database.objects.filter(owner=archive.owner)[:50]:
                meta = db_dir / f"{db.name}.meta.json"
                meta.write_text(
                    json.dumps({"name": db.name, "engine": getattr(db, "engine", "")}, indent=2),
                    encoding="utf-8",
                )
        except Exception:  # noqa: BLE001
            logger.debug("databases staging skip", exc_info=True)
        paths.append(db_dir)

    if "email" in includes:
        mail_dir = staging / "email"
        mail_dir.mkdir(parents=True, exist_ok=True)
        (mail_dir / "README.txt").write_text(
            "Email mailboxes placeholder — Maildir dump in live ops.\n",
            encoding="utf-8",
        )
        paths.append(mail_dir)

    manifest = {
        "owner": archive.owner.username,
        "name": archive.name,
        "includes": includes,
        "created_at": timezone.now().isoformat(),
        "engine": "restic",
    }
    man = staging / "manifest.json"
    man.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    paths.append(man)
    # Dédupliquer en gardant l'ordre
    seen: set[str] = set()
    unique: list[Path] = []
    for p in paths:
        key = str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _cleanup_staging(archive: BackupArchive) -> None:
    staging = config_root() / "staging" / str(archive.owner_id) / archive.name
    shutil.rmtree(staging, ignore_errors=True)


# ---------------------------------------------------------------------------
# Create / run / restore
# ---------------------------------------------------------------------------


def write_meta(archive: BackupArchive) -> Path:
    path = config_root() / "meta" / f"{archive.owner_id}_{archive.name}.json"
    path.write_text(
        json.dumps(
            {
                "id": archive.pk,
                "owner": archive.owner.username,
                "name": archive.name,
                "type": archive.backup_type,
                "includes": archive.includes,
                "status": archive.status,
                "snapshot_id": archive.snapshot_id,
                "size_bytes": archive.size_bytes,
                "checksum": archive.checksum,
                "destination_id": archive.destination_id,
                "progress": archive.progress,
                "duration_seconds": archive.duration_seconds,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


@transaction.atomic
def create_backup(
    *,
    owner: User,
    name: str = "",
    label: str = "",
    backup_type: str = BackupArchive.BackupType.FULL,
    includes: list | None = None,
    notes: str = "",
    destination_id: int | None = None,
    trigger: str = BackupArchive.Trigger.MANUAL,
    async_run: bool = True,
) -> BackupArchive:
    """Crée un job de backup et le lance (Celery async, sync en mock)."""
    _assert_backup_allowed(owner)
    if backup_type not in BackupArchive.BackupType.values:
        raise VZoneAPIException(detail="Type de sauvegarde invalide.", code="invalid_type", status_code=400)
    components = _normalize_includes(includes, backup_type)
    slug = (name or f"bk-{timezone.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}").strip().lower()
    slug = slug.replace(" ", "-")
    if not NAME_RE.match(slug):
        raise VZoneAPIException(detail="Nom de sauvegarde invalide.", code="invalid_name", status_code=400)
    if BackupArchive.objects.filter(owner=owner, name=slug).exists():
        raise VZoneAPIException(detail="Cette sauvegarde existe déjà.", code="exists", status_code=400)

    dest = resolve_destination(owner, destination_id)
    archive = BackupArchive.objects.create(
        owner=owner,
        destination=dest,
        name=slug,
        label=label or slug,
        backup_type=backup_type,
        trigger=trigger,
        includes=components,
        status=BackupArchive.Status.PENDING,
        file_name=f"{slug}.restic",
        notes=notes,
        progress=0,
    )
    write_meta(archive)
    _add_log(owner, BackupEventLog.Event.CREATE, archive=archive, message=f"queued {components}")
    archive_id = archive.pk
    # Mock / sync : exécuter dans le même appel (TestCase Django n'exécute pas on_commit)
    if (not async_run) or provision_mode() == "mock":
        return run_backup_job(archive_id)
    transaction.on_commit(lambda: _dispatch_backup_task(archive_id))
    return archive


def _dispatch_backup_task(archive_id: int) -> None:
    try:
        from apps.backups.tasks import execute_backup_job

        async_result = execute_backup_job.delay(archive_id)
        BackupArchive.objects.filter(pk=archive_id).update(celery_task_id=async_result.id or "")
    except Exception:  # noqa: BLE001
        logger.exception("Celery dispatch failed — run inline")
        run_backup_job(archive_id)


def run_backup_job(archive_id: int) -> BackupArchive:
    """Exécute réellement le backup Restic (appelé par Celery ou sync)."""
    archive = BackupArchive.objects.select_related("owner", "destination").get(pk=archive_id)
    if archive.status in {BackupArchive.Status.COMPLETED, BackupArchive.Status.RESTORED}:
        return archive

    archive.status = BackupArchive.Status.RUNNING
    archive.started_at = timezone.now()
    archive.progress = 5
    archive.append_log("backup job started")
    archive.save(update_fields=["status", "started_at", "progress", "log", "updated_at"])

    t0 = time.monotonic()
    try:
        if provision_mode() == "mock":
            _run_mock_backup(archive)
        else:
            _run_restic_backup(archive)
        archive.status = BackupArchive.Status.COMPLETED
        archive.completed_at = timezone.now()
        archive.progress = 100
        archive.duration_seconds = int(time.monotonic() - t0)
        archive.last_error = ""
        archive.append_log(f"completed in {archive.duration_seconds}s")
        archive.save()
        write_meta(archive)
        _add_log(
            archive.owner,
            BackupEventLog.Event.COMPLETE,
            archive=archive,
            message=f"snapshot={archive.snapshot_id[:12]} size={archive.size_bytes}",
        )
        # Rétention si schedule liée via notes/tag
        _maybe_apply_default_retention(archive)
    except Exception as exc:  # noqa: BLE001
        logger.exception("backup job %s failed", archive_id)
        archive.status = BackupArchive.Status.FAILED
        archive.last_error = str(exc)[:4000]
        archive.duration_seconds = int(time.monotonic() - t0)
        archive.progress = 100
        archive.append_log(f"FAILED: {exc}")
        archive.save()
        write_meta(archive)
        _add_log(
            archive.owner,
            BackupEventLog.Event.FAIL,
            archive=archive,
            success=False,
            message=str(exc),
        )
        _cleanup_staging(archive)
        raise
    _cleanup_staging(archive)
    return archive


def _run_mock_backup(archive: BackupArchive) -> None:
    archive.progress = 40
    archive.append_log("mock restic backup")
    archive.save(update_fields=["progress", "log", "updated_at"])
    payload = {
        "mock": True,
        "engine": "restic",
        "owner": archive.owner.username,
        "name": archive.name,
        "includes": archive.includes,
        "token": secrets.token_hex(8),
    }
    content = json.dumps(payload, indent=2).encode("utf-8")
    dest_dir = config_root() / "archives" / str(archive.owner_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{archive.name}.mock.json"
    path.write_bytes(content)
    archive.file_name = path.name
    archive.size_bytes = len(content)
    archive.checksum = hashlib.sha256(content).hexdigest()
    archive.snapshot_id = secrets.token_hex(16)
    archive.files_new = 1
    archive.progress = 90
    archive.append_log(f"mock snapshot {archive.snapshot_id}")
    archive.save()


def _run_restic_backup(archive: BackupArchive) -> None:
    from shutil import which

    from apps.backups.engine import restic as restic_mod

    if not which(restic_mod.restic_bin()):
        # Fallback tar si restic non installé (compat / restore tests live)
        _run_tar_backup(archive)
        return

    dest = archive.destination or resolve_destination(archive.owner)
    password, _creds, rclone_cfg = destination_credentials(dest)
    if not password:
        raise RuntimeError("Mot de passe Restic manquant pour la destination")

    def on_progress(pct: int, msg: str) -> None:
        archive.progress = max(archive.progress, min(99, pct))
        archive.append_log(msg)
        archive.save(update_fields=["progress", "log", "updated_at"])

    on_progress(15, "preparing sources")
    sources = _prepare_sources(archive)
    if not sources:
        raise RuntimeError("Aucune source à sauvegarder")

    # Init dépôt si besoin
    init = restic_mod.init_repository(
        repository=dest.repository_uri,
        password=password,
        rclone_config=rclone_cfg,
    )
    if not init.ok:
        raise RuntimeError(f"restic init: {init.output[:500]}")

    tags = [
        f"owner:{archive.owner_id}",
        f"name:{archive.name}",
        f"type:{archive.backup_type}",
        *[f"inc:{x}" for x in archive.includes],
    ]
    result, snap = restic_mod.backup_paths(
        repository=dest.repository_uri,
        password=password,
        paths=[str(p) for p in sources],
        tags=tags,
        host=f"vzone-{archive.owner.username}",
        rclone_config=rclone_cfg,
        exclude=["**/cache/**", "**/.cache/**", "**/node_modules/**"],
        on_progress=on_progress,
    )
    if not result.ok:
        raise RuntimeError(f"restic backup: {result.output[:1500]}")

    archive.append_log(result.stdout[-2000:] if result.stdout else result.stderr[-1000:])
    if snap:
        archive.snapshot_id = snap.id
        summary = snap.summary or {}
        archive.size_bytes = int(summary.get("data_added") or summary.get("total_bytes_processed") or 0)
        archive.files_new = int(summary.get("files_new") or 0)
        archive.files_changed = int(summary.get("files_changed") or 0)
        archive.files_unmodified = int(summary.get("files_unmodified") or 0)
        archive.checksum = (snap.id or "")[:64]
    else:
        snaps = restic_mod.list_snapshots(
            repository=dest.repository_uri,
            password=password,
            rclone_config=rclone_cfg,
            tags=[f"name:{archive.name}"],
        )
        if snaps:
            archive.snapshot_id = snaps[-1].id
            archive.checksum = snaps[-1].id[:64]
    archive.file_name = f"{archive.snapshot_id[:12] or archive.name}.restic"
    archive.save()


def _run_tar_backup(archive: BackupArchive) -> None:
    """Fallback archive tar.gz (sans restic)."""
    import io
    import sys
    import tarfile

    dest_dir = config_root() / "archives" / str(archive.owner_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{archive.name}.tar.gz"
    home = _account_home(archive.owner)
    with tarfile.open(dest, "w:gz") as tar:
        manifest = {
            "owner": archive.owner.username,
            "name": archive.name,
            "includes": archive.includes,
            "created_at": timezone.now().isoformat(),
            "engine": "tar-fallback",
        }
        manifest_path = dest.with_suffix(".manifest.json")
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        tar.add(manifest_path, arcname="manifest.json")
        manifest_path.unlink(missing_ok=True)
        if "home" in archive.includes and home.exists():
            tar.add(home, arcname="home", recursive=True)
        if "databases" in archive.includes:
            info = tarfile.TarInfo(name="databases/README.txt")
            payload = b"Database dumps placeholder\n"
            info.size = len(payload)
            tar.addfile(info, fileobj=io.BytesIO(payload))
        if "email" in archive.includes:
            info = tarfile.TarInfo(name="email/README.txt")
            payload = b"Email mailbox placeholder\n"
            info.size = len(payload)
            tar.addfile(info, fileobj=io.BytesIO(payload))
    data = dest.read_bytes()
    archive.file_name = dest.name
    archive.size_bytes = len(data)
    archive.checksum = hashlib.sha256(data).hexdigest()
    archive.snapshot_id = archive.checksum[:32]
    archive.append_log("tar fallback backup completed")
    archive.save()


def restore_backup(archive: BackupArchive, *, actor: User | None = None) -> BackupArchive:
    path_ok = bool(archive.snapshot_id) or (
        provision_mode() == "mock"
        and (config_root() / "archives" / str(archive.owner_id) / (archive.file_name or "")).exists()
    )
    restorable = {
        BackupArchive.Status.COMPLETED,
        BackupArchive.Status.RESTORED,
    }
    if archive.status == BackupArchive.Status.FAILED and path_ok:
        restorable = restorable | {BackupArchive.Status.FAILED}
    if archive.status not in restorable:
        raise VZoneAPIException(
            detail="Seules les sauvegardes terminées peuvent être restaurées.",
            code="invalid_status",
            status_code=400,
        )

    archive.status = BackupArchive.Status.RESTORING
    archive.progress = 5
    archive.append_log("restore started")
    archive.save(update_fields=["status", "progress", "log", "updated_at"])

    try:
        if provision_mode() == "mock":
            message = f"mock restore {archive.name}"
        else:
            message = _run_restic_restore(archive)
        archive.status = BackupArchive.Status.RESTORED
        archive.restored_at = timezone.now()
        archive.last_error = ""
        archive.progress = 100
        archive.append_log(message)
        archive.save()
        write_meta(archive)
        _add_log(archive.owner, BackupEventLog.Event.RESTORE, archive=archive, message=message)
        AuditLog.objects.create(
            actor=actor or archive.owner,
            action=AuditLog.Action.RESTORE,
            resource_type="backup",
            resource_id=str(archive.pk),
            message=message,
        )
    except VZoneAPIException as exc:
        _mark_restore_failed(archive, str(exc.detail))
        raise
    except Exception as exc:  # noqa: BLE001
        _mark_restore_failed(archive, str(exc))
        raise VZoneAPIException(
            detail=f"Échec de la restauration : {exc}",
            code="restore_failed",
            status_code=502,
            extra={"error": str(exc)},
        ) from exc
    return archive


def _run_restic_restore(archive: BackupArchive) -> str:
    from shutil import which
    import sys
    import tarfile

    from apps.backups.engine import restic as restic_mod

    # Fallback tar
    tar_path = config_root() / "archives" / str(archive.owner_id) / (archive.file_name or "")
    if tar_path.suffixes[-2:] == [".tar", ".gz"] or str(tar_path).endswith(".tar.gz") or (
        not which(restic_mod.restic_bin()) and tar_path.exists()
    ):
        return _run_tar_restore(archive, tar_path)

    if not archive.snapshot_id:
        raise VZoneAPIException(detail="Snapshot Restic manquant.", code="missing_snapshot", status_code=400)
    if not which(restic_mod.restic_bin()):
        if tar_path.exists():
            return _run_tar_restore(archive, tar_path)
        raise RuntimeError("restic non installé")

    dest = archive.destination or resolve_destination(archive.owner)
    password, _, rclone_cfg = destination_credentials(dest)
    password = password or ""
    target = config_root() / "staging" / "restore" / str(archive.owner_id) / archive.name
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)

    def on_progress(pct: int, msg: str) -> None:
        archive.progress = max(archive.progress, min(99, pct))
        archive.append_log(msg)
        archive.save(update_fields=["progress", "log", "updated_at"])

    result = restic_mod.restore_snapshot(
        repository=dest.repository_uri,
        password=password,
        snapshot_id=archive.snapshot_id,
        target=target,
        rclone_config=rclone_cfg,
        on_progress=on_progress,
    )
    if not result.ok:
        raise RuntimeError(result.output[:1500])

    parts: list[str] = []
    home_src = target / "home"
    if not home_src.exists():
        candidates = list(target.rglob("public_html"))
        if candidates:
            home_src = candidates[0].parent
    if "home" in (archive.includes or []) and home_src.exists():
        home = _account_home(archive.owner)
        home.mkdir(parents=True, exist_ok=True)
        for item in home_src.iterdir():
            dest_item = home / item.name
            if item.is_dir():
                if dest_item.exists():
                    shutil.rmtree(dest_item, ignore_errors=True)
                shutil.copytree(item, dest_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest_item)
        ensure_cpanel_tree(home)
        parts.append("home")
    if "databases" in (archive.includes or []):
        parts.append("databases")
    if "email" in (archive.includes or []):
        parts.append("email")
    shutil.rmtree(target, ignore_errors=True)
    return f"restored {', '.join(parts) or 'snapshot'} from {archive.snapshot_id[:12]}"


def _run_tar_restore(archive: BackupArchive, path: Path) -> str:
    import tarfile
    import sys

    if not path.exists():
        raise VZoneAPIException(detail="Fichier de sauvegarde introuvable.", code="missing_file", status_code=404)
    parts: list[str] = []
    if "home" in (archive.includes or []):
        home = _account_home(archive.owner)
        home.mkdir(parents=True, exist_ok=True)
        with tarfile.open(path, "r:*") as tar:
            dest_resolved = home.resolve()
            prefix = "home/"
            members = []
            for member in tar.getmembers():
                name = member.name.replace("\\", "/")
                if name.startswith("./"):
                    name = name[2:]
                if not name.startswith(prefix):
                    continue
                rel = name[len(prefix) :]
                if not rel or ".." in Path(rel).parts:
                    continue
                target = (home / rel).resolve()
                try:
                    target.relative_to(dest_resolved)
                except ValueError:
                    continue
                member.name = rel
                members.append(member)
            kwargs: dict = {"path": str(home), "members": members}
            if sys.version_info >= (3, 12):
                kwargs["filter"] = "data"
            if members:
                tar.extractall(**kwargs)
                parts.append(f"home ({len(members)} entrées)")
        ensure_cpanel_tree(home)
    if "databases" in (archive.includes or []):
        parts.append("databases")
    if "email" in (archive.includes or []):
        parts.append("email")
    return f"restored {', '.join(parts)} from {archive.name}"


def _mark_restore_failed(archive: BackupArchive, message: str) -> None:
    archive.status = BackupArchive.Status.COMPLETED
    archive.last_error = message[:4000]
    archive.append_log(f"restore failed: {message}")
    archive.save(update_fields=["status", "last_error", "log", "updated_at"])
    write_meta(archive)
    _add_log(
        archive.owner,
        BackupEventLog.Event.FAIL,
        archive=archive,
        success=False,
        message=message,
    )


@transaction.atomic
def delete_backup(archive: BackupArchive) -> None:
    # Note: on ne forget pas forcément le snapshot restic global (partagé dépôt)
    meta = config_root() / "meta" / f"{archive.owner_id}_{archive.name}.json"
    meta.unlink(missing_ok=True)
    mock = config_root() / "archives" / str(archive.owner_id) / (archive.file_name or "")
    mock.unlink(missing_ok=True)
    _cleanup_staging(archive)
    _add_log(archive.owner, BackupEventLog.Event.DELETE, archive=None, message=f"deleted {archive.name}")
    archive.delete()


def download_info(archive: BackupArchive) -> dict:
    if archive.status not in {
        BackupArchive.Status.COMPLETED,
        BackupArchive.Status.RESTORED,
    }:
        raise VZoneAPIException(
            detail="Sauvegarde non disponible au téléchargement.",
            code="invalid_status",
            status_code=400,
        )
    mock_path = config_root() / "archives" / str(archive.owner_id) / (archive.file_name or "")
    exists = mock_path.exists() or bool(archive.snapshot_id)
    _add_log(
        archive.owner,
        BackupEventLog.Event.DOWNLOAD,
        archive=archive,
        message=f"download {archive.file_name or archive.snapshot_id}",
    )
    return {
        "name": archive.name,
        "file_name": archive.file_name,
        "size_bytes": archive.size_bytes,
        "checksum": archive.checksum,
        "snapshot_id": archive.snapshot_id,
        "path": str(mock_path) if mock_path.exists() else archive.destination.repository_uri if archive.destination_id else "",
        "exists": exists,
        "engine": "restic",
        "download_token": secrets.token_urlsafe(16),
    }


# ---------------------------------------------------------------------------
# Schedules + retention
# ---------------------------------------------------------------------------


def _compute_next_run(schedule: BackupSchedule, now: datetime | None = None) -> datetime:
    now = now or timezone.now()
    base = now.replace(second=0, microsecond=0)
    if schedule.frequency == BackupSchedule.Frequency.HOURLY:
        nxt = base.replace(minute=min(schedule.minute, 59)) + timedelta(hours=1)
        if nxt <= now:
            nxt += timedelta(hours=1)
        return nxt
    if schedule.frequency == BackupSchedule.Frequency.DAILY:
        nxt = base.replace(hour=schedule.hour, minute=min(schedule.minute, 59))
        if nxt <= now:
            nxt += timedelta(days=1)
        return nxt
    if schedule.frequency == BackupSchedule.Frequency.WEEKLY:
        nxt = base.replace(hour=schedule.hour, minute=min(schedule.minute, 59))
        days_ahead = (schedule.weekday - nxt.weekday()) % 7
        nxt = nxt + timedelta(days=days_ahead)
        if nxt <= now:
            nxt += timedelta(days=7)
        return nxt
    # monthly — 1er du mois
    if now.day == 1 and now.hour < schedule.hour:
        return now.replace(day=1, hour=schedule.hour, minute=min(schedule.minute, 59))
    if now.month == 12:
        return now.replace(year=now.year + 1, month=1, day=1, hour=schedule.hour, minute=0)
    return now.replace(month=now.month + 1, day=1, hour=schedule.hour, minute=min(schedule.minute, 59))


@transaction.atomic
def upsert_schedule(
    *,
    owner: User,
    frequency: str = BackupSchedule.Frequency.WEEKLY,
    includes: list | None = None,
    hour: int = 2,
    minute: int = 0,
    weekday: int = 0,
    is_active: bool = True,
    notes: str = "",
    name: str = "",
    destination_id: int | None = None,
    keep_hourly: int = 0,
    keep_daily: int = 7,
    keep_weekly: int = 4,
    keep_monthly: int = 6,
    schedule_id: int | None = None,
) -> BackupSchedule:
    _assert_backup_feature(owner)
    if frequency not in BackupSchedule.Frequency.values:
        raise VZoneAPIException(detail="Fréquence invalide.", code="invalid_frequency", status_code=400)
    components = _normalize_includes(
        includes, BackupArchive.BackupType.CUSTOM if includes else BackupArchive.BackupType.FULL
    )
    hour = max(0, min(int(hour), 23))
    minute = max(0, min(int(minute), 59))
    weekday = max(0, min(int(weekday), 6))
    dest = resolve_destination(owner, destination_id)

    defaults = {
        "frequency": frequency,
        "includes": components,
        "hour": hour,
        "minute": minute,
        "weekday": weekday,
        "is_active": is_active,
        "notes": notes,
        "name": name or f"{frequency}-{hour:02d}h",
        "destination": dest,
        "keep_hourly": max(0, int(keep_hourly)),
        "keep_daily": max(0, int(keep_daily)),
        "keep_weekly": max(0, int(keep_weekly)),
        "keep_monthly": max(0, int(keep_monthly)),
    }
    if schedule_id:
        schedule = BackupSchedule.objects.filter(pk=schedule_id, owner=owner).first()
        if not schedule:
            raise VZoneAPIException(detail="Planning introuvable.", code="not_found", status_code=404)
        for k, v in defaults.items():
            setattr(schedule, k, v)
        schedule.next_run_at = _compute_next_run(schedule)
        schedule.save()
    else:
        # Compat: un seul schedule « principal » par owner+frequency si name vide
        schedule, _created = BackupSchedule.objects.update_or_create(
            owner=owner,
            name=defaults["name"],
            defaults={**defaults, "next_run_at": None},
        )
        schedule.next_run_at = _compute_next_run(schedule)
        schedule.save(update_fields=["next_run_at", "updated_at"])

    _add_log(
        owner,
        BackupEventLog.Event.SCHEDULE,
        message=f"{frequency} hour={hour} keep_d={keep_daily} active={is_active}",
    )
    return schedule


def delete_schedule(schedule: BackupSchedule) -> None:
    owner = schedule.owner
    schedule.delete()
    _add_log(owner, BackupEventLog.Event.SCHEDULE, message="schedule deleted")


def run_due_schedules(*, now: datetime | None = None) -> list[BackupArchive]:
    now = now or timezone.now()
    created: list[BackupArchive] = []
    for schedule in BackupSchedule.objects.filter(is_active=True).select_related("owner", "destination"):
        if schedule.last_run_at and (now - schedule.last_run_at).total_seconds() < 550:
            continue
        due = False
        if schedule.frequency == BackupSchedule.Frequency.HOURLY:
            due = now.minute == schedule.minute or (
                schedule.next_run_at and schedule.next_run_at <= now
            )
        elif schedule.frequency == BackupSchedule.Frequency.DAILY and now.hour == schedule.hour:
            due = schedule.minute <= now.minute < schedule.minute + 5 or now.minute == schedule.minute
        elif (
            schedule.frequency == BackupSchedule.Frequency.WEEKLY
            and now.weekday() == schedule.weekday
            and now.hour == schedule.hour
        ):
            due = True
        elif (
            schedule.frequency == BackupSchedule.Frequency.MONTHLY
            and now.day == 1
            and now.hour == schedule.hour
        ):
            due = True
        if schedule.next_run_at and schedule.next_run_at <= now:
            due = True
        if not due:
            continue
        try:
            archive = create_backup(
                owner=schedule.owner,
                backup_type=BackupArchive.BackupType.INCREMENTAL,
                includes=schedule.includes,
                label=f"scheduled-{schedule.frequency}",
                destination_id=schedule.destination_id,
                trigger=BackupArchive.Trigger.SCHEDULED,
                async_run=True,
            )
            schedule.last_run_at = now
            schedule.next_run_at = _compute_next_run(schedule, now)
            schedule.save(update_fields=["last_run_at", "next_run_at", "updated_at"])
            created.append(archive)
        except Exception:  # noqa: BLE001
            logger.exception("Échec backup planifié pour %s", schedule.owner.username)
    return created


def apply_retention(
    *,
    destination: BackupDestination,
    owner: User | None = None,
    keep_hourly: int = 0,
    keep_daily: int = 7,
    keep_weekly: int = 4,
    keep_monthly: int = 6,
) -> dict[str, Any]:
    if provision_mode() == "mock":
        return {"mock": True, "forgotten": 0}
    from apps.backups.engine import restic as restic_mod

    password, _, rclone_cfg = destination_credentials(destination)
    tags = [f"owner:{owner.pk}"] if owner else None
    result = restic_mod.forget_and_prune(
        repository=destination.repository_uri,
        password=password,
        keep_hourly=keep_hourly,
        keep_daily=keep_daily,
        keep_weekly=keep_weekly,
        keep_monthly=keep_monthly,
        tags=tags,
        rclone_config=rclone_cfg,
    )
    if owner:
        _add_log(
            owner,
            BackupEventLog.Event.PRUNE,
            success=result.ok,
            message=result.output[:2000] or "prune ok",
        )
    return {"ok": result.ok, "output": result.output[:2000]}


def _maybe_apply_default_retention(archive: BackupArchive) -> None:
    if not archive.destination_id:
        return
    sched = (
        BackupSchedule.objects.filter(owner=archive.owner, destination=archive.destination, is_active=True)
        .order_by("-updated_at")
        .first()
    )
    if not sched:
        return
    try:
        apply_retention(
            destination=archive.destination,
            owner=archive.owner,
            keep_hourly=sched.keep_hourly,
            keep_daily=sched.keep_daily,
            keep_weekly=sched.keep_weekly,
            keep_monthly=sched.keep_monthly,
        )
    except Exception:  # noqa: BLE001
        logger.exception("retention after backup failed")


def storage_usage(user: User) -> dict[str, Any]:
    qs = archives_qs(user).filter(status=BackupArchive.Status.COMPLETED)
    total = qs.aggregate(total=Sum("size_bytes"))["total"] or 0
    by_dest = list(
        qs.values("destination__name", "destination__provider")
        .annotate(total=Sum("size_bytes"), count=Sum("id"))
        .order_by()
    )
    return {
        "total_size_bytes": total,
        "archives": qs.count(),
        "by_destination": by_dest,
    }


def overview_for(user: User) -> dict:
    qs = archives_qs(user)
    total_size = qs.aggregate(total=Sum("size_bytes"))["total"] or 0
    return {
        "archives": qs.count(),
        "completed": qs.filter(status=BackupArchive.Status.COMPLETED).count(),
        "failed": qs.filter(status=BackupArchive.Status.FAILED).count(),
        "restored": qs.filter(status=BackupArchive.Status.RESTORED).count(),
        "running": qs.filter(status__in={BackupArchive.Status.PENDING, BackupArchive.Status.RUNNING}).count(),
        "total_size_bytes": total_size,
        "schedules": schedules_qs(user).filter(is_active=True).count(),
        "destinations": destinations_qs(user).filter(is_active=True).count(),
        "max_backups": int(getattr(settings, "VZONE_BACKUP_MAX", MAX_BACKUPS_DEFAULT)),
        "provision_mode": provision_mode(),
        "engine": "restic",
        "storage": "rclone",
    }


def prune_oldest(owner: User) -> None:
    limit = int(getattr(settings, "VZONE_BACKUP_MAX", MAX_BACKUPS_DEFAULT))
    if limit <= 0:
        return
    qs = BackupArchive.objects.filter(owner=owner).order_by("created_at")
    excess = qs.count() - limit
    if excess <= 0:
        return
    for archive in qs[:excess]:
        delete_backup(archive)
