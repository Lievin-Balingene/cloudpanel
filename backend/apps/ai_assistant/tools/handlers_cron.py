"""Tools cron."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


@register_tool(
    name="list_cron_jobs",
    description="Liste les tâches cron du compte + aperçu crontab.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_cron_jobs(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.cron.services import crontab_preview_for, jobs_queryset_for, overview_for

    jobs = [
        {
            "id": j.pk,
            "label": j.label or "",
            "command": j.command,
            "schedule": f"{j.minute} {j.hour} {j.day} {j.month} {j.weekday}",
            "common": j.common,
            "is_active": j.is_active,
        }
        for j in jobs_queryset_for(user)[:80]
    ]
    return ok(overview=overview_for(user), jobs=jobs, preview=crontab_preview_for(user)[:2000])


@register_tool(
    name="create_cron_job",
    description="Crée une tâche cron (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "common": {"type": "string"},
            "minute": {"type": "string"},
            "hour": {"type": "string"},
            "day": {"type": "string"},
            "month": {"type": "string"},
            "weekday": {"type": "string"},
            "label": {"type": "string"},
            "email_to": {"type": "string"},
        },
        "required": ["command"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_cron_job(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.cron.models import CronJob
    from apps.cron.services import create_cron_job as svc

    command = require_str(params, "command", max_len=2000)
    if not command:
        return err("command requis")

    def _run():
        job = svc(
            owner=user,
            command=command,
            common=require_str(params, "common", default=CronJob.Common.CUSTOM) or CronJob.Common.CUSTOM,
            minute=require_str(params, "minute", default="0") or "0",
            hour=require_str(params, "hour", default="*") or "*",
            day=require_str(params, "day", default="*") or "*",
            month=require_str(params, "month", default="*") or "*",
            weekday=require_str(params, "weekday", default="*") or "*",
            label=require_str(params, "label", max_len=120),
            email_to=require_str(params, "email_to", max_len=200),
        )
        return {"id": job.pk, "command": job.command, "label": job.label}

    return run_service(_run)


@register_tool(
    name="update_cron_job",
    description="Modifie une tâche cron (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "job_id": {"type": "integer"},
            "command": {"type": "string"},
            "common": {"type": "string"},
            "minute": {"type": "string"},
            "hour": {"type": "string"},
            "day": {"type": "string"},
            "month": {"type": "string"},
            "weekday": {"type": "string"},
            "label": {"type": "string"},
            "is_active": {"type": "boolean"},
        },
        "required": ["job_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def update_cron_job(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.cron.services import jobs_queryset_for, update_cron_job as svc

    job = jobs_queryset_for(user).filter(pk=require_int(params, "job_id")).first()
    if not job:
        return err("Job introuvable", "not_found")
    fields = {}
    for key in ("command", "common", "minute", "hour", "day", "month", "weekday", "label"):
        if key in params and params[key] is not None:
            fields[key] = params[key]
    if "is_active" in params:
        fields["is_active"] = bool(params["is_active"])

    def _run():
        updated = svc(job, **fields)
        return {"id": updated.pk, "command": updated.command, "is_active": updated.is_active}

    return run_service(_run)


@register_tool(
    name="delete_cron_job",
    description="Supprime une tâche cron (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"job_id": {"type": "integer"}},
        "required": ["job_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_cron_job(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.cron.services import delete_cron_job as svc, jobs_queryset_for

    job = jobs_queryset_for(user).filter(pk=require_int(params, "job_id")).first()
    if not job:
        return err("Job introuvable", "not_found")
    jid = job.pk

    def _run():
        svc(job)
        return {"deleted": jid}

    return run_service(_run)


@register_tool(
    name="sync_cron_jobs",
    description="Resynchronise le crontab système du compte (confirmation requise).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    dangerous=True,
)
def sync_cron_jobs(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.cron.services import request_cron_sync

    return run_service(lambda: request_cron_sync(user))
