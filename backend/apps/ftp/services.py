"""Services FTP : quotas, CRUD, suspension, provisionnement, journaux."""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.files.services import user_home
from apps.ftp.models import FtpAccount, FtpLog

logger = logging.getLogger(__name__)

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,62}$")


def accounts_queryset_for(user: User) -> QuerySet[FtpAccount]:
    qs = FtpAccount.objects.select_related("owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def logs_queryset_for(user: User) -> QuerySet[FtpLog]:
    qs = FtpLog.objects.select_related("account", "owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user) | Q(account__owner__parent=user))
    return qs.filter(Q(owner=user) | Q(account__owner=user))


def _assert_ftp_quota(owner: User) -> None:
    quota = getattr(owner, "quota", None)
    if quota is None:
        return
    limit = quota.ftp_accounts
    if limit == 0 and owner.role == User.Role.ADMINISTRATOR:
        return
    current = FtpAccount.objects.filter(owner=owner).count()
    if limit > 0 and current >= limit:
        raise QuotaExceeded(
            detail="Quota de comptes FTP atteint.",
            extra={"limit": limit, "used": current},
        )


def _normalize_username(username: str, owner: User) -> str:
    raw = username.strip().lower()
    if "@" in raw or raw.startswith(f"{owner.username}_"):
        candidate = raw.replace("@", "_")
    else:
        # Préfixe type cPanel : user_ftpname
        candidate = f"{owner.username}_{raw}" if not raw.startswith(f"{owner.username}_") else raw
    if not USERNAME_RE.match(candidate):
        raise VZoneAPIException(
            detail="Nom d'utilisateur FTP invalide (a-z, 0-9, ._- ; min 3).",
            code="invalid_username",
            status_code=400,
        )
    return candidate


def resolve_ftp_directory(owner: User, relative_directory: str) -> tuple[str, Path]:
    rel = (relative_directory or "public_html").replace("\\", "/").strip("/")
    if ".." in Path(rel).parts:
        raise VZoneAPIException(
            detail="Répertoire FTP invalide.",
            code="invalid_directory",
            status_code=400,
        )
    home = user_home(owner)
    target = (home / rel).resolve()
    try:
        target.relative_to(home)
    except ValueError as exc:
        raise VZoneAPIException(
            detail="Répertoire hors du home autorisé.",
            code="path_forbidden",
            status_code=403,
        ) from exc
    target.mkdir(parents=True, exist_ok=True)
    return rel, target


def write_virtual_users_file() -> Path | None:
    """Exporte les comptes actifs au format Pure-FTPd virtual users (si activé)."""
    export_path = getattr(settings, "VZONE_FTP_VIRTUAL_USERS_FILE", None)
    if not export_path:
        return None
    path = Path(export_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for account in FtpAccount.objects.filter(is_active=True, is_suspended=False).order_by("username"):
        # Format simplifié login:uid:gid:home:password_hash
        lines.append(
            f"{account.username}:vzone:vzone:{account.directory}:{account.password_hash}"
        )
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def provision_account(account: FtpAccount) -> None:
    """Provisionne le home et synchronise le fichier virtual users."""
    Path(account.directory).mkdir(parents=True, exist_ok=True)
    try:
        write_virtual_users_file()
    except OSError:
        logger.exception("Échec écriture virtual users FTP")


@transaction.atomic
def create_ftp_account(
    *,
    owner: User,
    username: str,
    password: str,
    relative_directory: str = "public_html",
    quota_mb: int = 0,
    bandwidth_kbs: int = 0,
    can_write: bool = True,
    notes: str = "",
) -> FtpAccount:
    if len(password) < 8:
        raise VZoneAPIException(
            detail="Mot de passe FTP trop court (min 8).",
            code="weak_password",
            status_code=400,
        )
    _assert_ftp_quota(owner)
    login = _normalize_username(username, owner)
    if FtpAccount.objects.filter(username=login).exists():
        raise VZoneAPIException(
            detail="Ce compte FTP existe déjà.",
            code="exists",
            status_code=400,
        )
    rel, absolute = resolve_ftp_directory(owner, relative_directory)
    account = FtpAccount(
        owner=owner,
        username=login,
        directory=str(absolute),
        relative_directory=rel,
        quota_mb=quota_mb,
        bandwidth_kbs=bandwidth_kbs,
        can_write=can_write,
        notes=notes,
    )
    account.set_password(password)
    account.save()
    provision_account(account)
    record_log(
        event_type=FtpLog.EventType.SYSTEM,
        account=account,
        owner=owner,
        username=login,
        message="Compte FTP créé",
        success=True,
    )
    return account


@transaction.atomic
def update_ftp_account(
    account: FtpAccount,
    *,
    password: str | None = None,
    relative_directory: str | None = None,
    quota_mb: int | None = None,
    bandwidth_kbs: int | None = None,
    can_write: bool | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
) -> FtpAccount:
    if password is not None:
        if len(password) < 8:
            raise VZoneAPIException(
                detail="Mot de passe FTP trop court (min 8).",
                code="weak_password",
                status_code=400,
            )
        account.set_password(password)
    if relative_directory is not None:
        rel, absolute = resolve_ftp_directory(account.owner, relative_directory)
        account.relative_directory = rel
        account.directory = str(absolute)
    if quota_mb is not None:
        account.quota_mb = quota_mb
    if bandwidth_kbs is not None:
        account.bandwidth_kbs = bandwidth_kbs
    if can_write is not None:
        account.can_write = can_write
    if notes is not None:
        account.notes = notes
    if is_active is not None:
        account.is_active = is_active
    account.save()
    provision_account(account)
    record_log(
        event_type=FtpLog.EventType.SYSTEM,
        account=account,
        owner=account.owner,
        username=account.username,
        message="Compte FTP modifié",
        success=True,
    )
    return account


@transaction.atomic
def suspend_ftp_account(account: FtpAccount, suspended: bool = True) -> FtpAccount:
    account.is_suspended = suspended
    if suspended:
        account.is_active = False
    else:
        account.is_active = True
    account.save(update_fields=["is_suspended", "is_active", "updated_at"])
    provision_account(account)
    record_log(
        event_type=FtpLog.EventType.SYSTEM,
        account=account,
        owner=account.owner,
        username=account.username,
        message="Compte FTP suspendu" if suspended else "Compte FTP réactivé",
        success=True,
    )
    return account


@transaction.atomic
def delete_ftp_account(account: FtpAccount, *, remove_directory: bool = False) -> None:
    username = account.username
    owner = account.owner
    directory = account.directory
    account.delete()
    write_virtual_users_file()
    if remove_directory:
        path = Path(directory)
        home = user_home(owner)
        try:
            path.relative_to(home)
            if path.exists() and path != home and path.name not in {"public_html", "mail", "tmp", "logs"}:
                shutil.rmtree(path, ignore_errors=True)
        except ValueError:
            pass
    record_log(
        event_type=FtpLog.EventType.SYSTEM,
        account=None,
        owner=owner,
        username=username,
        message="Compte FTP supprimé",
        success=True,
    )


def record_log(
    *,
    event_type: str,
    account: FtpAccount | None = None,
    owner: User | None = None,
    username: str = "",
    path: str = "",
    bytes_transferred: int = 0,
    ip_address: str | None = None,
    message: str = "",
    success: bool = True,
) -> FtpLog:
    if account and event_type == FtpLog.EventType.LOGIN and success:
        account.last_login_at = timezone.now()
        account.last_login_ip = ip_address
        account.save(update_fields=["last_login_at", "last_login_ip", "updated_at"])
    return FtpLog.objects.create(
        account=account,
        owner=owner or (account.owner if account else None),
        event_type=event_type,
        username=username or (account.username if account else ""),
        path=path,
        bytes_transferred=bytes_transferred,
        ip_address=ip_address,
        message=message,
        success=success,
    )


def authenticate_ftp(username: str, password: str, ip_address: str | None = None) -> FtpAccount | None:
    """Auth utilisée par un daemon FTP / hook PAM / API interne."""
    try:
        account = FtpAccount.objects.select_related("owner").get(username=username.lower())
    except FtpAccount.DoesNotExist:
        record_log(
            event_type=FtpLog.EventType.LOGIN_FAILED,
            username=username,
            ip_address=ip_address,
            message="Utilisateur inconnu",
            success=False,
        )
        return None
    if account.is_suspended or not account.is_active:
        record_log(
            event_type=FtpLog.EventType.LOGIN_FAILED,
            account=account,
            owner=account.owner,
            username=username,
            ip_address=ip_address,
            message="Compte suspendu ou inactif",
            success=False,
        )
        return None
    if not account.check_password(password):
        record_log(
            event_type=FtpLog.EventType.LOGIN_FAILED,
            account=account,
            owner=account.owner,
            username=username,
            ip_address=ip_address,
            message="Mot de passe invalide",
            success=False,
        )
        return None
    record_log(
        event_type=FtpLog.EventType.LOGIN,
        account=account,
        owner=account.owner,
        username=username,
        ip_address=ip_address,
        message="Connexion réussie",
        success=True,
    )
    return account
