"""Tâches Celery — backups Restic async."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="backups.execute_backup_job", bind=True, max_retries=1)
def execute_backup_job(self, archive_id: int) -> dict:
    from apps.backups.services import run_backup_job

    try:
        archive = run_backup_job(archive_id)
        return {
            "id": archive.pk,
            "status": archive.status,
            "snapshot_id": archive.snapshot_id,
            "size_bytes": archive.size_bytes,
            "duration_seconds": archive.duration_seconds,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("execute_backup_job %s", archive_id)
        return {"id": archive_id, "status": "failed", "error": str(exc)}


@shared_task(name="backups.execute_restore_job")
def execute_restore_job(archive_id: int) -> dict:
    from apps.backups.models import BackupArchive
    from apps.backups.services import restore_backup

    archive = BackupArchive.objects.get(pk=archive_id)
    archive = restore_backup(archive)
    return {"id": archive.pk, "status": archive.status}


@shared_task(name="backups.run_due_schedules")
def run_due_backup_schedules() -> dict:
    from apps.backups.services import run_due_schedules

    created = run_due_schedules()
    return {"created": len(created), "ids": [a.pk for a in created]}


@shared_task(name="backups.apply_retention")
def apply_retention_task(
    destination_id: int,
    owner_id: int | None = None,
    keep_hourly: int = 0,
    keep_daily: int = 7,
    keep_weekly: int = 4,
    keep_monthly: int = 6,
) -> dict:
    from apps.accounts.models import User
    from apps.backups.models import BackupDestination
    from apps.backups.services import apply_retention

    dest = BackupDestination.objects.get(pk=destination_id)
    owner = User.objects.filter(pk=owner_id).first() if owner_id else None
    return apply_retention(
        destination=dest,
        owner=owner,
        keep_hourly=keep_hourly,
        keep_daily=keep_daily,
        keep_weekly=keep_weekly,
        keep_monthly=keep_monthly,
    )
