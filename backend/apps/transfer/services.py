"""Orchestration Transfer Tool."""
from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException
from apps.transfer.models import TransferJob
from apps.transfer.pkgacct import extract_archive, find_account_root, inspect_bundle
from apps.transfer.remote import WhmRemoteClient
from apps.transfer.restore import restore_account

logger = logging.getLogger(__name__)


def transfer_root() -> Path:
    root = Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "transfer"
    root.mkdir(parents=True, exist_ok=True)
    (root / "uploads").mkdir(exist_ok=True)
    (root / "work").mkdir(exist_ok=True)
    return root


def default_options() -> dict:
    return {
        "home": True,
        "domains": True,
        "dns": True,
        "databases": True,
        "email": True,
        "ssl": True,
        "ftp": True,
    }


def _set_progress(job: TransferJob, percent: int, step: str) -> None:
    job.progress = max(0, min(100, percent))
    job.current_step = step
    job.append_log(step)
    job.save(update_fields=["progress", "current_step", "log", "updated_at"])


def inspect_uploaded_archive(archive_path: Path) -> dict:
    work = transfer_root() / "work" / f"inspect-{archive_path.stem}-{timezone.now().strftime('%H%M%S')}"
    try:
        extract_archive(archive_path, work)
        root = find_account_root(work)
        bundle = inspect_bundle(root)
        from apps.transfer.pkgacct import list_mailboxes_from_va, list_mysql_dumps, list_userdata_domains

        return {
            "username": bundle.username,
            "main_domain": bundle.main_domain,
            "contact_email": bundle.contact_email,
            "has_homedir": bool(bundle.homedir),
            "domains": list_userdata_domains(bundle),
            "databases": [{"name": d["name"], "engine": d["engine"]} for d in list_mysql_dumps(bundle)],
            "mailboxes": len(list_mailboxes_from_va(bundle)),
            "has_dns": bool(bundle.dnszones_dir),
            "has_ssl": bool(bundle.ssl_dir or bundle.apache_tls_dir),
            "warnings": bundle.warnings,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def remote_list_accounts(
    *,
    host: str,
    port: int,
    user: str,
    token: str,
    insecure_ssl: bool = False,
    ssh_port: int = 22,
) -> dict:
    client = WhmRemoteClient(
        host,
        port=port,
        user=user,
        token=token,
        insecure_ssl=insecure_ssl,
        ssh_port=ssh_port,
    )
    ver = client.version()
    accounts = client.list_accounts()
    return {
        "version": ver,
        "accounts": accounts,
        "count": len(accounts),
        "auth_method": client.auth_method,
    }


def start_job_async(job_id: int) -> None:
    thread = threading.Thread(target=_run_job, args=(job_id,), daemon=True, name=f"transfer-{job_id}")
    thread.start()


def _run_job(job_id: int) -> None:
    close_old_connections()
    try:
        job = TransferJob.objects.get(pk=job_id)
    except TransferJob.DoesNotExist:
        return
    job.status = TransferJob.Status.RUNNING
    job.started_at = timezone.now()
    job.last_error = ""
    job.save(update_fields=["status", "started_at", "last_error", "updated_at"])

    work: Path | None = None
    try:
        opts = {**default_options(), **(job.options or {})}

        def log(msg: str) -> None:
            job.append_log(msg)
            job.save(update_fields=["log", "updated_at"])

        archive_path: Path | None = None
        if job.source_type == TransferJob.SourceType.REMOTE_WHM:
            _set_progress(job, 5, "Connexion WHM distant…")
            client = WhmRemoteClient(
                job.remote_host,
                port=job.remote_port,
                user=job.remote_user or "root",
                token=job.remote_token,
                insecure_ssl=job.remote_insecure_ssl,
                ssh_port=getattr(job, "remote_ssh_port", None) or 22,
                timeout=180,
            )
            remote_user = (job.remote_username or job.username or "").strip()
            if not remote_user:
                raise VZoneAPIException(
                    detail="Compte distant non spécifié.",
                    code="missing_remote_user",
                    status_code=400,
                )
            # Vérifie l'auth tôt
            try:
                client.version()
            except VZoneAPIException:
                raise
            log(f"WHM authentifié ({client.auth_method or 'ok'}) — {job.remote_host}:{job.remote_port}")
            dest = transfer_root() / "uploads" / f"remote-{job.id}-cpmove-{remote_user}.tar.gz"

            def remote_progress(pct: int, step: str) -> None:
                # Packaging/download : garder dans 5–60
                mapped = max(5, min(60, int(pct) if pct <= 100 else 55))
                _set_progress(job, mapped, step)

            _set_progress(job, 8, f"Packaging + téléchargement cpmove de {remote_user}…")
            archive_path = client.package_and_fetch(
                remote_user,
                dest,
                progress=remote_progress,
            )
            job.archive_path = str(archive_path)
            job.archive_name = archive_path.name
            job.save(update_fields=["archive_path", "archive_name", "updated_at"])
            _set_progress(job, 58, f"Archive distante prête ({archive_path.name})")

        if not job.archive_path and not archive_path:
            raise VZoneAPIException(detail="Archive manquante.", code="missing_archive", status_code=400)
        archive_path = Path(job.archive_path) if not archive_path else archive_path
        if not archive_path.is_file():
            raise VZoneAPIException(detail="Fichier archive introuvable.", code="archive_missing", status_code=400)

        _set_progress(job, 62, "Extraction archive cPanel…")
        work = transfer_root() / "work" / f"job-{job.id}"
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        extract_archive(archive_path, work)
        root = find_account_root(work)
        _set_progress(job, 70, "Analyse structure pkgacct…")
        bundle = inspect_bundle(root, username_override=job.username)

        _set_progress(job, 75, "Restauration compte (home, domaines, mail, DB)…")
        result = restore_account(
            bundle,
            username=job.username or bundle.username,
            email=job.email or bundle.contact_email,
            password=job.password,
            package_name=job.package_name,
            overwrite=job.overwrite,
            options=opts,
            log=log,
        )
        _set_progress(job, 95, "Finalisation…")

        created = User.objects.filter(username=result["username"]).first()
        job.created_user = created
        job.result = {
            **result,
            # Ne pas renvoyer le mot de passe en clair dans les listes ultérieures si déjà lu
            "password": result.get("password", ""),
        }
        job.status = TransferJob.Status.COMPLETED
        job.progress = 100
        job.current_step = "Terminé"
        job.finished_at = timezone.now()
        job.remote_token = ""  # purge
        job.append_log("SUCCESS")
        job.save()
    except VZoneAPIException as exc:
        job.status = TransferJob.Status.FAILED
        job.last_error = str(exc.detail)
        job.current_step = "Échec"
        job.finished_at = timezone.now()
        job.remote_token = ""
        job.append_log(f"ERROR: {exc.detail}")
        job.save()
        logger.exception("Transfer job %s failed", job_id)
    except Exception as exc:  # noqa: BLE001
        job.status = TransferJob.Status.FAILED
        job.last_error = str(exc)
        job.current_step = "Échec"
        job.finished_at = timezone.now()
        job.remote_token = ""
        job.append_log(f"ERROR: {exc}")
        job.save()
        logger.exception("Transfer job %s failed", job_id)
    finally:
        if work and work.exists():
            shutil.rmtree(work, ignore_errors=True)
        close_old_connections()


def create_archive_job(
    *,
    actor: User,
    archive_path: Path,
    archive_name: str,
    username: str,
    email: str = "",
    password: str = "",
    package_name: str = "",
    overwrite: bool = False,
    options: dict | None = None,
) -> TransferJob:
    job = TransferJob.objects.create(
        initiated_by=actor,
        source_type=TransferJob.SourceType.ARCHIVE,
        username=username.strip().lower(),
        email=email.strip(),
        password=password,
        package_name=package_name.strip(),
        overwrite=overwrite,
        archive_name=archive_name,
        archive_path=str(archive_path),
        options={**default_options(), **(options or {})},
        status=TransferJob.Status.PENDING,
        current_step="En file d'attente",
    )
    start_job_async(job.id)
    return job


def create_remote_job(
    *,
    actor: User,
    host: str,
    port: int,
    whm_user: str,
    token: str,
    remote_username: str,
    email: str = "",
    password: str = "",
    package_name: str = "",
    overwrite: bool = False,
    insecure_ssl: bool = False,
    ssh_port: int = 22,
    options: dict | None = None,
) -> TransferJob:
    job = TransferJob.objects.create(
        initiated_by=actor,
        source_type=TransferJob.SourceType.REMOTE_WHM,
        username=remote_username.strip().lower(),
        remote_username=remote_username.strip().lower(),
        email=email.strip(),
        password=password,
        package_name=package_name.strip(),
        overwrite=overwrite,
        remote_host=host.strip(),
        remote_port=port,
        remote_user=whm_user.strip() or "root",
        remote_token=token.strip(),
        remote_insecure_ssl=insecure_ssl,
        remote_ssh_port=int(ssh_port or 22),
        options={**default_options(), **(options or {})},
        status=TransferJob.Status.PENDING,
        current_step="En file d'attente",
    )
    start_job_async(job.id)
    return job
