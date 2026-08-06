"""Services Cron Jobs — CRUD + sync vers /etc/cron.d via agent root."""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.cron.models import CronJob
from apps.files.services import user_home

logger = logging.getLogger(__name__)

# Caractères autorisés dans un champ cron (cPanel-like)
CRON_FIELD_RE = re.compile(r"^[0-9*,\-/\sA-Za-z]+$")
COMMON_SCHEDULES: dict[str, tuple[str, str, str, str, str]] = {
    CronJob.Common.ONCE_PER_MINUTE: ("*", "*", "*", "*", "*"),
    CronJob.Common.ONCE_PER_FIVE: ("*/5", "*", "*", "*", "*"),
    CronJob.Common.TWICE_PER_HOUR: ("0,30", "*", "*", "*", "*"),
    CronJob.Common.ONCE_PER_HOUR: ("0", "*", "*", "*", "*"),
    CronJob.Common.TWICE_PER_DAY: ("0", "0,12", "*", "*", "*"),
    CronJob.Common.ONCE_PER_DAY: ("0", "0", "*", "*", "*"),
    CronJob.Common.ONCE_PER_WEEK: ("0", "0", "*", "*", "0"),
    CronJob.Common.ONCE_PER_MONTH: ("0", "0", "1", "*", "*"),
    CronJob.Common.ONCE_PER_YEAR: ("0", "0", "1", "1", "*"),
}


def jobs_queryset_for(user: User) -> QuerySet[CronJob]:
    qs = CronJob.objects.select_related("owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def _cron_limit(owner: User) -> int:
    """0 = illimité. Sinon limite package.cron_jobs (défaut 10)."""
    if owner.role == User.Role.ADMINISTRATOR:
        return 0
    try:
        assignment = getattr(owner, "package_assignment", None)
        if assignment and assignment.package_id:
            return int(assignment.package.cron_jobs)
    except Exception:  # noqa: BLE001
        logger.debug("cron limit package skip", exc_info=True)
    return 10


def _assert_cron_quota(owner: User) -> None:
    limit = _cron_limit(owner)
    if limit == 0:
        return
    used = CronJob.objects.filter(owner=owner).count()
    if used >= limit:
        raise QuotaExceeded(
            detail="Quota de tâches cron atteint.",
            extra={"limit": limit, "used": used},
        )


def _validate_cron_field(name: str, value: str) -> str:
    v = (value or "").strip()
    if not v or len(v) > 64 or not CRON_FIELD_RE.match(v):
        raise VZoneAPIException(
            detail=f"Champ cron invalide : {name}.",
            code="invalid_cron_field",
            status_code=400,
            extra={"field": name, "value": value},
        )
    if "\n" in v or "\r" in v:
        raise VZoneAPIException(
            detail=f"Champ cron invalide : {name}.",
            code="invalid_cron_field",
            status_code=400,
        )
    return v


def _validate_command(command: str) -> str:
    cmd = (command or "").strip()
    if not cmd:
        raise VZoneAPIException(
            detail="La commande est obligatoire.",
            code="command_required",
            status_code=400,
        )
    if "\n" in cmd or "\r" in cmd:
        raise VZoneAPIException(
            detail="La commande ne doit pas contenir de retours à la ligne.",
            code="invalid_command",
            status_code=400,
        )
    if len(cmd) > 4000:
        raise VZoneAPIException(
            detail="Commande trop longue.",
            code="command_too_long",
            status_code=400,
        )
    # Anti escalade : pas de sudo/su ni chemins système sensibles
    lowered = cmd.lower()
    blocked = (
        "sudo",
        "pkexec",
        "runuser",
        "doas",
        "/etc/passwd",
        "/etc/shadow",
        "/etc/sudoers",
        "/root/",
        "chmod 777 /",
        "chown root",
    )
    for token in blocked:
        if token in lowered:
            raise VZoneAPIException(
                detail=f"Commande refusée (motif sécurité: {token}).",
                code="command_forbidden",
                status_code=400,
            )
    if re.search(r"(^|[\s;|&`])su(\s|$)", cmd):
        raise VZoneAPIException(
            detail="Commande refusée (su).",
            code="command_forbidden",
            status_code=400,
        )
    return cmd


def apply_common_schedule(common: str) -> tuple[str, str, str, str, str] | None:
    return COMMON_SCHEDULES.get(common)


def cron_run_user() -> str:
    """Déprécié — les jobs doivent tourner sous system_username du compte."""
    return str(getattr(settings, "VZONE_CRON_RUN_USER", None) or "vzone")


def system_user_for(owner: User) -> str:
    return (owner.system_username or owner.username or "").strip().lower()


def _cron_run_as(owner: User) -> str:
    """UID Linux du compte — jamais root/vzone pour un client."""
    from apps.accounts.linux_users import ensure_linux_user, jail_username_for
    from apps.accounts.services import RESERVED_USERNAMES

    name = jail_username_for(owner)
    if name in RESERVED_USERNAMES or name in {"root", "vzone"}:
        raise VZoneAPIException(
            detail="Compte système invalide pour cron.",
            code="invalid_cron_user",
            status_code=400,
        )
    ensure_linux_user(owner)
    return name


def jobs_dir() -> Path:
    root = Path(
        getattr(settings, "VZONE_CRON_JOBS_DIR", None)
        or (Path(settings.VZONE_DATA_ROOT) / "cron" / "jobs")
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_cron_d_content(owner: User, jobs: list[CronJob]) -> str:
    """Génère le fichier /etc/cron.d/vzone-<user> (format cron.d = 6 champs + user)."""
    home = user_home(owner)
    run_as = _cron_run_as(owner)
    mailto = ""
    for job in jobs:
        if job.is_active and job.email_to:
            mailto = job.email_to.strip()
            break

    lines = [
        "# Managed by V-zone Panel — do not edit manually",
        f"# account={system_user_for(owner)} home={home}",
        "SHELL=/bin/bash",
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"HOME={home}",
    ]
    if mailto:
        lines.append(f"MAILTO={mailto}")
    else:
        lines.append('MAILTO=""')
    lines.append("")

    active = [j for j in jobs if j.is_active]
    if not active:
        lines.append("# (no active jobs)")
        lines.append("")
        return "\n".join(lines)

    log_dir = home / "logs"
    for job in active:
        label = (job.label or f"job-{job.pk}").replace("\n", " ").strip()
        lines.append(f"# VZONE_ID={job.pk} {label}")
        cmd = (
            f"cd {home} && ( {job.command} ) "
            f">>{log_dir}/cron-{job.pk}.log 2>&1"
        )
        cmd_safe = cmd.replace("%", "\\%")
        lines.append(
            f"{job.minute} {job.hour} {job.day} {job.month} {job.weekday} "
            f"{run_as} {cmd_safe}"
        )
        lines.append("")
    return "\n".join(lines)


def request_cron_sync(owner: User) -> dict:
    """Dépose un job pour l'agent root (écriture /etc/cron.d/)."""
    username = system_user_for(owner)
    if not username or not re.match(r"^[a-z][a-z0-9_-]{1,31}$", username):
        raise VZoneAPIException(
            detail="system_username invalide pour cron.",
            code="invalid_system_user",
            status_code=400,
        )

    jobs = list(CronJob.objects.filter(owner=owner).order_by("id"))
    content = build_cron_d_content(owner, jobs)
    filename = f"vzone-{username}"
    payload = {
        "username": username,
        "filename": filename,
        "content": content,
        "home": str(user_home(owner)),
        "requested_at": int(time.time()),
    }

    # Mode mock / sans agent : écrire un fichier local de prévisualisation
    mode = (getattr(settings, "VZONE_CRON_PROVISION_MODE", "auto") or "auto").lower()
    preview = Path(settings.VZONE_DATA_ROOT) / "cron" / "preview" / f"{filename}"
    try:
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_text(content, encoding="utf-8")
    except OSError:
        logger.debug("cron preview write skip", exc_info=True)

    if mode == "mock":
        return {"mode": "mock", "filename": filename, "jobs": len(jobs)}

    job_path = jobs_dir() / f"{username}-{int(time.time() * 1000)}.request"
    try:
        job_path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        raise VZoneAPIException(
            detail=f"Impossible d'écrire la demande cron : {exc}",
            code="cron_queue_failed",
            status_code=500,
        ) from exc

    # Tenter de déclencher l'agent immédiatement
    try:
        import subprocess

        subprocess.run(
            ["systemctl", "start", "vzone-cron-job.service"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return {"mode": "live", "filename": filename, "jobs": len(jobs), "request": str(job_path)}


@transaction.atomic
def create_cron_job(
    *,
    owner: User,
    command: str,
    common: str = CronJob.Common.CUSTOM,
    minute: str = "0",
    hour: str = "*",
    day: str = "*",
    month: str = "*",
    weekday: str = "*",
    email_to: str = "",
    label: str = "",
    is_active: bool = True,
) -> CronJob:
    _assert_cron_quota(owner)
    common = common or CronJob.Common.CUSTOM
    if common not in CronJob.Common.values:
        raise VZoneAPIException(detail="Preset invalide.", code="invalid_common", status_code=400)

    schedule = apply_common_schedule(common)
    if schedule:
        minute, hour, day, month, weekday = schedule

    job = CronJob.objects.create(
        owner=owner,
        common=common,
        minute=_validate_cron_field("minute", minute),
        hour=_validate_cron_field("hour", hour),
        day=_validate_cron_field("day", day),
        month=_validate_cron_field("month", month),
        weekday=_validate_cron_field("weekday", weekday),
        command=_validate_command(command),
        email_to=(email_to or "").strip(),
        label=(label or "").strip()[:120],
        is_active=bool(is_active),
    )
    request_cron_sync(owner)
    return job


@transaction.atomic
def update_cron_job(job: CronJob, **fields) -> CronJob:
    if "common" in fields and fields["common"] is not None:
        common = fields["common"]
        if common not in CronJob.Common.values:
            raise VZoneAPIException(detail="Preset invalide.", code="invalid_common", status_code=400)
        job.common = common
        schedule = apply_common_schedule(common)
        if schedule:
            job.minute, job.hour, job.day, job.month, job.weekday = schedule

    for key in ("minute", "hour", "day", "month", "weekday"):
        if key in fields and fields[key] is not None and job.common == CronJob.Common.CUSTOM:
            setattr(job, key, _validate_cron_field(key, fields[key]))

    if "command" in fields and fields["command"] is not None:
        job.command = _validate_command(fields["command"])
    if "email_to" in fields and fields["email_to"] is not None:
        job.email_to = str(fields["email_to"]).strip()
    if "label" in fields and fields["label"] is not None:
        job.label = str(fields["label"]).strip()[:120]
    if "is_active" in fields and fields["is_active"] is not None:
        job.is_active = bool(fields["is_active"])

    job.save()
    request_cron_sync(job.owner)
    return job


@transaction.atomic
def delete_cron_job(job: CronJob) -> None:
    owner = job.owner
    job.delete()
    request_cron_sync(owner)


def overview_for(user: User) -> dict:
    qs = jobs_queryset_for(user)
    limit = _cron_limit(user)
    used = CronJob.objects.filter(owner=user).count() if user.role == User.Role.CLIENT else qs.count()
    return {
        "jobs": qs.count(),
        "active": qs.filter(is_active=True).count(),
        "inactive": qs.filter(is_active=False).count(),
        "quota_limit": limit,
        "quota_used": used,
        "home_path": str(user_home(user)),
        "common_presets": [{"value": c.value, "label": c.label} for c in CronJob.Common],
    }


def crontab_preview_for(owner: User) -> str:
    jobs = list(CronJob.objects.filter(owner=owner).order_by("id"))
    return build_cron_d_content(owner, jobs)
