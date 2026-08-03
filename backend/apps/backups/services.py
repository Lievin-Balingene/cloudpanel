"""Services backups : create / restore / schedule (mock ou live)."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.backups.models import BackupArchive, BackupEventLog, BackupSchedule
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.core.models import AuditLog
from apps.files.services import user_home

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,47}$")
VALID_INCLUDES = frozenset({"home", "databases", "email"})
MAX_BACKUPS_DEFAULT = 10


def archives_qs(user: User) -> QuerySet[BackupArchive]:
    qs = BackupArchive.objects.select_related("owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def schedules_qs(user: User) -> QuerySet[BackupSchedule]:
    qs = BackupSchedule.objects.select_related("owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_BACKUP_PROVISION_MODE", "auto").lower()
    return mode if mode in {"auto", "live", "mock"} else "auto"


def config_root() -> Path:
    root = Path(
        getattr(settings, "VZONE_BACKUP_DIR", None) or (Path(settings.VZONE_DATA_ROOT) / "backups")
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "archives").mkdir(exist_ok=True)
    (root / "meta").mkdir(exist_ok=True)
    return root


def owner_archive_dir(owner: User) -> Path:
    path = config_root() / "archives" / str(owner.pk)
    path.mkdir(parents=True, exist_ok=True)
    return path


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
        status=BackupArchive.Status.FAILED
    ).count()
    if limit > 0 and used >= limit:
        raise QuotaExceeded(
            detail="Quota de sauvegardes atteint.",
            extra={"limit": limit, "used": used},
        )


def _normalize_includes(includes: list | None, backup_type: str) -> list[str]:
    if backup_type == BackupArchive.BackupType.FULL:
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
                "file_name": archive.file_name,
                "size_bytes": archive.size_bytes,
                "checksum": archive.checksum,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _archive_path(archive: BackupArchive) -> Path:
    return owner_archive_dir(archive.owner) / (archive.file_name or f"{archive.name}.tar.gz")


def _build_live_archive(archive: BackupArchive) -> tuple[Path, int, str]:
    dest = _archive_path(archive)
    home = user_home(archive.owner)
    with tarfile.open(dest, "w:gz") as tar:
        manifest = {
            "owner": archive.owner.username,
            "name": archive.name,
            "includes": archive.includes,
            "created_at": timezone.now().isoformat(),
        }
        manifest_path = dest.with_suffix(".manifest.json")
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        tar.add(manifest_path, arcname="manifest.json")
        manifest_path.unlink(missing_ok=True)
        if "home" in archive.includes and home.exists():
            tar.add(home, arcname="home", recursive=True)
        if "databases" in archive.includes:
            info = tarfile.TarInfo(name="databases/README.txt")
            payload = b"Database dumps placeholder - integrate dumps in live ops.\n"
            info.size = len(payload)
            tar.addfile(info, fileobj=__import__("io").BytesIO(payload))
        if "email" in archive.includes:
            info = tarfile.TarInfo(name="email/README.txt")
            payload = b"Email mailbox placeholder - integrate Maildir dump in live ops.\n"
            info.size = len(payload)
            tar.addfile(info, fileobj=__import__("io").BytesIO(payload))
    data = dest.read_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    return dest, len(data), checksum


def _build_mock_archive(archive: BackupArchive) -> tuple[Path, int, str]:
    dest = _archive_path(archive)
    payload = {
        "mock": True,
        "owner": archive.owner.username,
        "name": archive.name,
        "includes": archive.includes,
        "token": secrets.token_hex(8),
    }
    content = json.dumps(payload, indent=2).encode("utf-8")
    dest.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    return dest, len(content), checksum


@transaction.atomic
def create_backup(
    *,
    owner: User,
    name: str = "",
    label: str = "",
    backup_type: str = BackupArchive.BackupType.FULL,
    includes: list | None = None,
    notes: str = "",
) -> BackupArchive:
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

    archive = BackupArchive.objects.create(
        owner=owner,
        name=slug,
        label=label or slug,
        backup_type=backup_type,
        includes=components,
        status=BackupArchive.Status.RUNNING,
        file_name=f"{slug}.tar.gz",
        notes=notes,
    )
    write_meta(archive)
    _add_log(owner, BackupEventLog.Event.CREATE, archive=archive, message=f"started {components}")

    try:
        if provision_mode() == "mock":
            path, size, checksum = _build_mock_archive(archive)
        else:
            path, size, checksum = _build_live_archive(archive)
        archive.size_bytes = size
        archive.checksum = checksum
        archive.status = BackupArchive.Status.COMPLETED
        archive.completed_at = timezone.now()
        archive.last_error = ""
        archive.save()
        write_meta(archive)
        _add_log(
            owner,
            BackupEventLog.Event.COMPLETE,
            archive=archive,
            message=f"completed {path.name} ({size} bytes)",
        )
    except Exception as exc:
        archive.status = BackupArchive.Status.FAILED
        archive.last_error = str(exc)
        archive.save(update_fields=["status", "last_error", "updated_at"])
        write_meta(archive)
        _add_log(
            owner,
            BackupEventLog.Event.FAIL,
            archive=archive,
            success=False,
            message=str(exc),
        )
        raise VZoneAPIException(
            detail="Échec de la sauvegarde.",
            code="backup_failed",
            status_code=502,
            extra={"error": str(exc)},
        ) from exc
    return archive


def restore_backup(archive: BackupArchive, *, actor: User | None = None) -> BackupArchive:
    if archive.status not in {
        BackupArchive.Status.COMPLETED,
        BackupArchive.Status.RESTORED,
    }:
        raise VZoneAPIException(
            detail="Seules les sauvegardes terminées peuvent être restaurées.",
            code="invalid_status",
            status_code=400,
        )
    archive.status = BackupArchive.Status.RESTORING
    archive.save(update_fields=["status", "updated_at"])

    try:
        path = _archive_path(archive)
        if not path.exists():
            raise VZoneAPIException(
                detail="Fichier de sauvegarde introuvable.",
                code="missing_file",
                status_code=404,
            )
        if provision_mode() == "mock":
            message = f"mock restore {archive.name}"
        else:
            if "home" in (archive.includes or []):
                home = user_home(archive.owner)
                home.mkdir(parents=True, exist_ok=True)
                if tarfile.is_tarfile(path):
                    with tarfile.open(path, "r:gz") as tar:
                        members = [m for m in tar.getmembers() if m.name.startswith("home/")]
                        tar.extractall(path=home.parent, members=members, filter="data")
                message = f"restored home from {archive.name}"
            else:
                message = f"restore noted for {archive.name} (no home component)"
        archive.status = BackupArchive.Status.RESTORED
        archive.restored_at = timezone.now()
        archive.last_error = ""
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
        archive.status = BackupArchive.Status.FAILED
        archive.last_error = str(exc.detail)
        archive.save(update_fields=["status", "last_error", "updated_at"])
        _add_log(
            archive.owner,
            BackupEventLog.Event.FAIL,
            archive=archive,
            success=False,
            message=str(exc.detail),
        )
        raise
    except Exception as exc:
        archive.status = BackupArchive.Status.FAILED
        archive.last_error = str(exc)
        archive.save(update_fields=["status", "last_error", "updated_at"])
        _add_log(
            archive.owner,
            BackupEventLog.Event.FAIL,
            archive=archive,
            success=False,
            message=str(exc),
        )
        raise VZoneAPIException(
            detail="Échec de la restauration.",
            code="restore_failed",
            status_code=502,
            extra={"error": str(exc)},
        ) from exc
    return archive


@transaction.atomic
def delete_backup(archive: BackupArchive) -> None:
    path = _archive_path(archive)
    if path.exists():
        path.unlink(missing_ok=True)
    meta = config_root() / "meta" / f"{archive.owner_id}_{archive.name}.json"
    if meta.exists():
        meta.unlink(missing_ok=True)
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
    path = _archive_path(archive)
    if not path.exists():
        raise VZoneAPIException(detail="Fichier introuvable.", code="missing_file", status_code=404)
    _add_log(
        archive.owner,
        BackupEventLog.Event.DOWNLOAD,
        archive=archive,
        message=f"download {archive.file_name}",
    )
    return {
        "name": archive.name,
        "file_name": archive.file_name,
        "size_bytes": archive.size_bytes,
        "checksum": archive.checksum,
        "path": str(path),
        "exists": True,
        "download_token": secrets.token_urlsafe(16),
    }


@transaction.atomic
def upsert_schedule(
    *,
    owner: User,
    frequency: str = BackupSchedule.Frequency.WEEKLY,
    includes: list | None = None,
    hour: int = 2,
    weekday: int = 0,
    is_active: bool = True,
    notes: str = "",
) -> BackupSchedule:
    _assert_backup_feature(owner)
    if frequency not in BackupSchedule.Frequency.values:
        raise VZoneAPIException(detail="Fréquence invalide.", code="invalid_frequency", status_code=400)
    components = _normalize_includes(includes, BackupArchive.BackupType.CUSTOM if includes else BackupArchive.BackupType.FULL)
    hour = max(0, min(int(hour), 23))
    weekday = max(0, min(int(weekday), 6))
    schedule, _created = BackupSchedule.objects.update_or_create(
        owner=owner,
        defaults={
            "frequency": frequency,
            "includes": components,
            "hour": hour,
            "weekday": weekday,
            "is_active": is_active,
            "notes": notes,
        },
    )
    _add_log(
        owner,
        BackupEventLog.Event.SCHEDULE,
        message=f"{frequency} hour={hour} active={is_active}",
    )
    return schedule


def delete_schedule(schedule: BackupSchedule) -> None:
    owner = schedule.owner
    schedule.delete()
    _add_log(owner, BackupEventLog.Event.SCHEDULE, message="schedule deleted")


def run_due_schedules(*, now: datetime | None = None) -> list[BackupArchive]:
    """Exécute les plannings dus (appelable depuis Celery / management)."""
    now = now or timezone.now()
    created: list[BackupArchive] = []
    for schedule in BackupSchedule.objects.filter(is_active=True).select_related("owner"):
        if schedule.last_run_at and (now - schedule.last_run_at).total_seconds() < 3600:
            continue
        due = False
        if schedule.frequency == BackupSchedule.Frequency.DAILY and now.hour == schedule.hour:
            due = True
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
        if not due:
            continue
        try:
            archive = create_backup(
                owner=schedule.owner,
                backup_type=BackupArchive.BackupType.CUSTOM,
                includes=schedule.includes,
                label=f"scheduled-{schedule.frequency}",
            )
            schedule.last_run_at = now
            schedule.save(update_fields=["last_run_at", "updated_at"])
            created.append(archive)
        except Exception:
            logger.exception("Échec backup planifié pour %s", schedule.owner.username)
    return created


def overview_for(user: User) -> dict:
    qs = archives_qs(user)
    total_size = qs.aggregate(total=Sum("size_bytes"))["total"] or 0
    return {
        "archives": qs.count(),
        "completed": qs.filter(status=BackupArchive.Status.COMPLETED).count(),
        "failed": qs.filter(status=BackupArchive.Status.FAILED).count(),
        "restored": qs.filter(status=BackupArchive.Status.RESTORED).count(),
        "total_size_bytes": total_size,
        "schedules": schedules_qs(user).filter(is_active=True).count(),
        "max_backups": int(getattr(settings, "VZONE_BACKUP_MAX", MAX_BACKUPS_DEFAULT)),
        "provision_mode": provision_mode(),
    }


def prune_oldest(owner: User) -> None:
    """Supprime les plus anciennes si au-dessus du quota (utilitaire)."""
    limit = int(getattr(settings, "VZONE_BACKUP_MAX", MAX_BACKUPS_DEFAULT))
    if limit <= 0:
        return
    qs = BackupArchive.objects.filter(owner=owner).order_by("created_at")
    excess = qs.count() - limit
    if excess <= 0:
        return
    for archive in qs[:excess]:
        delete_backup(archive)


def cleanup_owner_dir(owner: User) -> None:
    path = owner_archive_dir(owner)
    if path.exists() and not any(path.iterdir()):
        shutil.rmtree(path, ignore_errors=True)
