"""Tools sauvegardes (archives + planifications)."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


@register_tool(
    name="list_backups",
    description="Liste les archives, planifications et aperçu backups du compte.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_backups(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.backups.services import archives_qs, overview_for, schedules_qs

    archives = [
        {
            "id": a.pk,
            "name": a.name,
            "label": a.label or "",
            "backup_type": a.backup_type,
            "status": a.status,
            "size_bytes": a.size_bytes,
            "trigger": a.trigger,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        }
        for a in archives_qs(user).order_by("-created_at")[:40]
    ]
    schedules = [
        {
            "id": s.pk,
            "name": s.name,
            "frequency": s.frequency,
            "hour": s.hour,
            "minute": s.minute,
            "weekday": s.weekday,
            "is_active": s.is_active,
            "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
        }
        for s in schedules_qs(user)[:40]
    ]
    return ok(overview=overview_for(user), archives=archives, schedules=schedules)


@register_tool(
    name="create_backup",
    description="Lance une sauvegarde du compte (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "label": {"type": "string"},
            "backup_type": {"type": "string"},
            "includes": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"},
            "destination_id": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_backup(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.backups.models import BackupArchive
    from apps.backups.services import create_backup as svc

    includes = params.get("includes")
    if includes is not None and not isinstance(includes, list):
        return err("includes doit être une liste")

    def _run():
        archive = svc(
            owner=user,
            name=require_str(params, "name", max_len=80),
            label=require_str(params, "label", max_len=120),
            backup_type=require_str(params, "backup_type", default=BackupArchive.BackupType.FULL)
            or BackupArchive.BackupType.FULL,
            includes=includes,
            notes=require_str(params, "notes", max_len=200),
            destination_id=require_int(params, "destination_id"),
        )
        return {
            "id": archive.pk,
            "name": archive.name,
            "status": archive.status,
            "backup_type": archive.backup_type,
        }

    return run_service(_run)


@register_tool(
    name="restore_backup",
    description="Restaure une archive de sauvegarde (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"archive_id": {"type": "integer"}},
        "required": ["archive_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def restore_backup(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.backups.services import archives_qs, restore_backup as svc

    archive = archives_qs(user).filter(pk=require_int(params, "archive_id")).first()
    if not archive:
        return err("Archive introuvable", "not_found")

    def _run():
        restored = svc(archive, actor=user)
        return {"id": restored.pk, "name": restored.name, "status": restored.status}

    return run_service(_run)


@register_tool(
    name="delete_backup",
    description="Supprime une archive de sauvegarde (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"archive_id": {"type": "integer"}},
        "required": ["archive_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_backup(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.backups.services import archives_qs, delete_backup as svc

    archive = archives_qs(user).filter(pk=require_int(params, "archive_id")).first()
    if not archive:
        return err("Archive introuvable", "not_found")
    name = archive.name

    def _run():
        svc(archive)
        return {"deleted": name}

    return run_service(_run)


@register_tool(
    name="upsert_backup_schedule",
    description="Crée ou met à jour une planification de sauvegarde (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "schedule_id": {"type": "integer"},
            "name": {"type": "string"},
            "frequency": {"type": "string"},
            "includes": {"type": "array", "items": {"type": "string"}},
            "hour": {"type": "integer"},
            "minute": {"type": "integer"},
            "weekday": {"type": "integer"},
            "is_active": {"type": "boolean"},
            "notes": {"type": "string"},
            "destination_id": {"type": "integer"},
            "keep_hourly": {"type": "integer"},
            "keep_daily": {"type": "integer"},
            "keep_weekly": {"type": "integer"},
            "keep_monthly": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    dangerous=True,
)
def upsert_backup_schedule(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.backups.models import BackupSchedule
    from apps.backups.services import upsert_schedule

    includes = params.get("includes")
    if includes is not None and not isinstance(includes, list):
        return err("includes doit être une liste")

    def _run():
        schedule = upsert_schedule(
            owner=user,
            frequency=require_str(params, "frequency", default=BackupSchedule.Frequency.WEEKLY)
            or BackupSchedule.Frequency.WEEKLY,
            includes=includes,
            hour=require_int(params, "hour") if "hour" in params else 2,
            minute=require_int(params, "minute") if "minute" in params else 0,
            weekday=require_int(params, "weekday") if "weekday" in params else 0,
            is_active=bool(params["is_active"]) if "is_active" in params else True,
            notes=require_str(params, "notes", max_len=200),
            name=require_str(params, "name", max_len=80),
            destination_id=require_int(params, "destination_id"),
            keep_hourly=require_int(params, "keep_hourly") if "keep_hourly" in params else 0,
            keep_daily=require_int(params, "keep_daily") if "keep_daily" in params else 7,
            keep_weekly=require_int(params, "keep_weekly") if "keep_weekly" in params else 4,
            keep_monthly=require_int(params, "keep_monthly") if "keep_monthly" in params else 6,
            schedule_id=require_int(params, "schedule_id"),
        )
        return {
            "id": schedule.pk,
            "name": schedule.name,
            "frequency": schedule.frequency,
            "is_active": schedule.is_active,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        }

    return run_service(_run)


@register_tool(
    name="delete_backup_schedule",
    description="Supprime une planification de sauvegarde (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"schedule_id": {"type": "integer"}},
        "required": ["schedule_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_backup_schedule(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.backups.services import delete_schedule, schedules_qs

    schedule = schedules_qs(user).filter(pk=require_int(params, "schedule_id")).first()
    if not schedule:
        return err("Planification introuvable", "not_found")
    sid = schedule.pk

    def _run():
        delete_schedule(schedule)
        return {"deleted": sid}

    return run_service(_run)
