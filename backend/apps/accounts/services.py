"""Services métier comptes : JWT, 2FA, audit de connexion, homes cPanel."""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from pathlib import Path

import pyotp
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, UserSession
from apps.core.exceptions import VZoneAPIException
from apps.core.models import AuditLog

logger = logging.getLogger(__name__)

# Style cPanel : commence par une lettre, alphanumérique / _ / -, 3–32 car.
SYSTEM_USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")
RESERVED_USERNAMES = frozenset(
    {
        "admin",
        "root",
        "vzone",
        "vmail",
        "nobody",
        "www",
        "mail",
        "ftp",
        "mysql",
        "postgres",
    }
)


def normalize_system_username(username: str) -> str:
    return (username or "").strip().lower()


def validate_system_username(username: str) -> str:
    name = normalize_system_username(username)
    if not SYSTEM_USERNAME_RE.match(name):
        raise VZoneAPIException(
            detail=(
                "Nom d'utilisateur invalide (style cPanel) : "
                "3–32 caractères, commencer par une lettre, "
                "uniquement a-z, 0-9, _ ou -."
            ),
            code="invalid_username",
            status_code=400,
        )
    if name in RESERVED_USERNAMES:
        raise VZoneAPIException(
            detail=f"Le nom d'utilisateur « {name} » est réservé.",
            code="reserved_username",
            status_code=400,
        )
    return name


def provision_account_home(user: User) -> Path:
    """
    Crée le home du compte comme cPanel : VZONE_HOME_ROOT/<username>/
    avec public_html, mail, etc., et renseigne system_username / home_directory.
    """
    from apps.files.services import ensure_cpanel_tree, personal_home

    if user.role == User.Role.ADMINISTRATOR:
        sys_name = (user.system_username or "admin").strip().lower() or "admin"
    else:
        sys_name = validate_system_username(user.system_username or user.username)
        if user.username != sys_name:
            if not User.objects.filter(username=sys_name).exclude(pk=user.pk).exists():
                user.username = sys_name

    user.system_username = sys_name

    home = personal_home(user)
    try:
        ensure_cpanel_tree(home)
        index = home / "public_html" / "index.html"
        if not index.exists():
            index.write_text(
                "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
                f"<title>{sys_name}</title></head>"
                f"<body><h1>Account {sys_name}</h1>"
                "<p>V-zone Panel — document root (public_html).</p></body></html>\n",
                encoding="utf-8",
            )
    except OSError as exc:
        raise VZoneAPIException(
            detail=f"Impossible de créer le home {home}: {exc}",
            code="home_provision_failed",
            status_code=500,
        ) from exc

    user.home_directory = str(home)
    user.save(
        update_fields=["username", "system_username", "home_directory", "updated_at"]
    )
    logger.info("Home provisionné pour %s → %s", user.username, home)
    return home


def delete_account(user: User) -> None:
    """Supprime le compte et son home (sauf le home admin partagé)."""
    import shutil

    from django.conf import settings

    from apps.files.services import personal_home

    home_path: Path | None = None
    if user.role != User.Role.ADMINISTRATOR:
        try:
            home_path = personal_home(user)
        except Exception:  # noqa: BLE001
            home_path = None

    username = user.username
    user.delete()

    if home_path is not None and home_path.exists():
        root = Path(settings.VZONE_HOME_ROOT).resolve()
        try:
            resolved = home_path.resolve()
            if resolved != root and root in resolved.parents:
                shutil.rmtree(resolved, ignore_errors=True)
                logger.info("Home supprimé pour %s → %s", username, resolved)
        except OSError as exc:
            logger.warning("Échec suppression home %s: %s", home_path, exc)


def issue_tokens(user: User, request=None) -> dict:  # type: ignore[no-untyped-def]
    """Émet access + refresh JWT et enregistre la session."""
    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    jti = str(refresh["jti"])
    expires_at = timezone.now() + timedelta(
        seconds=int(refresh.access_token.lifetime.total_seconds())
    )

    ip = None
    ua = ""
    if request is not None:
        ip = _client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")[:512]
        user.last_login_ip = ip
        user.save(update_fields=["last_login_ip", "last_login"])

    UserSession.objects.create(
        user=user,
        jti=jti,
        user_agent=ua,
        ip_address=ip,
        expires_at=timezone.now() + refresh.lifetime,
    )

    AuditLog.objects.create(
        actor=user,
        action=AuditLog.Action.LOGIN,
        resource_type="user",
        resource_id=str(user.pk),
        message="Connexion réussie",
        ip_address=ip,
        user_agent=ua,
        request_id=getattr(request, "request_id", ""),
    )

    return {
        "access": str(access),
        "refresh": str(refresh),
        "expires_at": expires_at.isoformat(),
        "must_change_password": user.must_change_password,
    }


def revoke_refresh_token(token_str: str, user: User | None = None) -> None:
    token = RefreshToken(token_str)
    jti = str(token["jti"])
    token.blacklist()
    UserSession.objects.filter(jti=jti).update(is_revoked=True)
    if user is not None:
        AuditLog.objects.create(
            actor=user,
            action=AuditLog.Action.LOGOUT,
            resource_type="user",
            resource_id=str(user.pk),
            message="Déconnexion",
        )


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(user: User, otp: str) -> bool:
    if not user.two_factor_secret:
        return False
    totp = pyotp.TOTP(user.two_factor_secret)
    return totp.verify(otp, valid_window=1)


def provisioning_uri(user: User) -> str:
    if not user.two_factor_secret:
        user.two_factor_secret = generate_totp_secret()
        user.save(update_fields=["two_factor_secret"])
    totp = pyotp.TOTP(user.two_factor_secret)
    return totp.provisioning_uri(name=user.email, issuer_name="V-zone Panel")


def _client_ip(request) -> str | None:  # type: ignore[no-untyped-def]
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
