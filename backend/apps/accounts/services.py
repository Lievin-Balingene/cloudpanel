"""Services métier comptes : JWT, 2FA, audit de connexion."""
from __future__ import annotations

from datetime import timedelta

import pyotp
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, UserSession
from apps.core.models import AuditLog


def issue_tokens(user: User, request=None) -> dict:  # type: ignore[no-untyped-def]
    """Émet access + refresh JWT et enregistre la session."""
    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    jti = str(refresh["jti"])
    expires_at = timezone.now() + timedelta(seconds=int(refresh.access_token.lifetime.total_seconds()))

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
