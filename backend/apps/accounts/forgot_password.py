"""Mot de passe oublié — double preuve e-mail (lien one-shot + code).

Sécurité :
- Réponse identique (anti-énumération)
- Token + code stockés uniquement en HMAC-SHA256 (pepper SECRET_KEY)
- TTL court, usage unique, invalidation des défis précédents
- Rate-limit IP + identifiant (cache) + throttle DRF
- Tentatives code limitées → invalidation
- Nouveau MDP validé (Django + policy sécurité)
- Révocation sessions / JWT ; pas d'auto-login
- Aucun plaintext MDP dans les e-mails
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import time
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PasswordResetChallenge, User
from apps.core.exceptions import VZoneAPIException
from apps.core.models import AuditLog

logger = logging.getLogger(__name__)

TOKEN_BYTES = 32
CODE_LENGTH = 8
# Alphabet sans ambiguïté (pas 0/O, 1/I/l)
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TTL_MINUTES = 20
MAX_CODE_ATTEMPTS = 5
# Rate limits supplémentaires (au-delà du throttle DRF)
IP_REQUEST_LIMIT = 5
IP_REQUEST_WINDOW = 3600
ID_REQUEST_LIMIT = 3
ID_REQUEST_WINDOW = 3600
CONFIRM_IP_LIMIT = 20
CONFIRM_IP_WINDOW = 3600

GENERIC_REQUEST_MSG = (
    "Si un compte correspond, un e-mail avec un lien et un code de vérification "
    "a été envoyé. Vérifiez aussi vos indésirables."
)


def _pepper_hash(raw: str) -> str:
    key = (getattr(settings, "SECRET_KEY", "") or "vzone").encode("utf-8")
    return hmac.new(key, raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _normalize_identifier(value: str) -> str:
    return (value or "").strip()


def _generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def _generate_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _format_code_display(code: str) -> str:
    code = (code or "").upper().replace(" ", "").replace("-", "")
    if len(code) == CODE_LENGTH:
        return f"{code[:4]}-{code[4:]}"
    return code


def _normalize_code(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (code or "")).upper()


def _client_meta(request) -> tuple[str | None, str]:  # type: ignore[no-untyped-def]
    ip = None
    ua = ""
    if request is None:
        return ip, ua
    try:
        from apps.security.services import client_ip

        ip = client_ip(request)
    except Exception:  # noqa: BLE001
        ip = (getattr(request, "META", {}) or {}).get("REMOTE_ADDR")
    ua = ((getattr(request, "META", {}) or {}).get("HTTP_USER_AGENT") or "")[:512]
    return ip, ua


def _cache_bump(key: str, limit: int, window: int) -> None:
    """Incrémente un compteur cache ; lève si limite dépassée."""
    try:
        current = cache.get(key)
        if current is None:
            cache.set(key, 1, window)
            return
        if int(current) >= limit:
            raise VZoneAPIException(
                detail="Trop de tentatives. Réessayez plus tard.",
                code="forgot_password_rate_limited",
                status_code=429,
            )
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, int(current) + 1, window)
    except VZoneAPIException:
        raise
    except Exception:  # noqa: BLE001
        logger.debug("forgot-password cache rate skip", exc_info=True)


def _resolve_portal(request, explicit: str = "") -> str:  # type: ignore[no-untyped-def]
    from apps.security.portal import request_portal

    portal = (explicit or "").strip().lower()
    if portal not in {"admin", "client"}:
        portal = (request_portal(request) or "").strip().lower()
    if portal == "shared":
        portal = "client"
    if portal not in {"admin", "client"}:
        portal = "admin"
    return portal


def _reset_base_url(portal: str, request=None) -> str:  # type: ignore[no-untyped-def]
    from apps.server_setup.contact_notify import panel_hostname

    host = panel_hostname()
    # Prefer Host header if it looks like a real hostname (TLS / IP access)
    if request is not None:
        http_host = (request.META.get("HTTP_HOST") or "").split(":")[0].strip()
        if http_host and http_host not in {"localhost", "127.0.0.1"}:
            host = http_host
    admin_port = int(getattr(settings, "VZONE_ADMIN_PORT", 9086) or 9086)
    client_port = int(getattr(settings, "VZONE_CLIENT_PORT", 9082) or 9082)
    port = admin_port if portal == "admin" else client_port
    scheme = "https"
    if request is not None:
        xf = (request.META.get("HTTP_X_FORWARDED_PROTO") or "").split(",")[0].strip()
        if xf in {"http", "https"}:
            scheme = xf
        elif getattr(request, "scheme", None) in {"http", "https"}:
            scheme = request.scheme
    return f"{scheme}://{host}:{port}"


def _forgot_enabled() -> bool:
    try:
        from apps.server_setup.models import ServerSetup

        tweaks = ServerSetup.get_solo().tweak_settings or {}
        if "allow_forgot_password" in tweaks:
            return bool(tweaks["allow_forgot_password"])
    except Exception:  # noqa: BLE001
        pass
    return True


def _find_user(identifier: str) -> User | None:
    ident = _normalize_identifier(identifier)
    if not ident:
        return None
    qs = User.objects.filter(is_active=True, is_suspended=False)
    if "@" in ident:
        user = qs.filter(email__iexact=ident).first()
        if user:
            return user
    user = qs.filter(username__iexact=ident).first()
    if user:
        return user
    return qs.filter(email__iexact=ident).first()


def _send_reset_email(
    *,
    user: User,
    raw_token: str,
    raw_code: str,
    portal: str,
    request=None,
) -> bool:  # type: ignore[no-untyped-def]
    from apps.server_setup.contact_notify import _from_email_for_user

    to = (user.email or "").strip()
    if not to or "@" not in to:
        logger.warning("forgot-password: user %s sans e-mail valide", user.username)
        return False

    from apps.accounts.mail_templates import password_reset_bodies, send_branded_mail

    from_email = _from_email_for_user(user)
    base = _reset_base_url(portal, request)
    link = f"{base}/reset-password?token={raw_token}"
    code_disp = _format_code_display(raw_code)
    subject = "AngaPanel — réinitialisation du mot de passe"
    text_body, html_body = password_reset_bodies(
        username=user.username,
        reset_link=link,
        code_display=code_disp,
        ttl_minutes=TTL_MINUTES,
    )
    try:
        send_branded_mail(
            subject=subject,
            to=to,
            from_email=from_email,
            text_body=text_body,
            html_body=html_body,
        )
        logger.info(
            "forgot-password e-mail envoyé à user_id=%s from=%s to=%s",
            user.pk,
            from_email,
            to,
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception("forgot-password: échec envoi e-mail user_id=%s", user.pk)
        return False


@transaction.atomic
def request_password_reset(
    *,
    identifier: str,
    request=None,
    portal: str = "",
) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Démarre le flux. Réponse toujours générique (anti-énumération)."""
    started = time.monotonic()
    if not _forgot_enabled():
        raise VZoneAPIException(
            detail="La réinitialisation par e-mail est désactivée.",
            code="forgot_password_disabled",
            status_code=403,
        )

    ident = _normalize_identifier(identifier)
    ip, ua = _client_meta(request)
    if ip:
        _cache_bump(f"fp:req:ip:{ip}", IP_REQUEST_LIMIT, IP_REQUEST_WINDOW)
    if ident:
        id_key = hashlib.sha256(ident.lower().encode()).hexdigest()[:32]
        _cache_bump(f"fp:req:id:{id_key}", ID_REQUEST_LIMIT, ID_REQUEST_WINDOW)

    portal_resolved = _resolve_portal(request, portal)
    user = _find_user(ident) if ident else None

    if user is not None:
        # Invalide les défis ouverts
        PasswordResetChallenge.objects.filter(
            user=user, consumed_at__isnull=True
        ).update(consumed_at=timezone.now())

        raw_token = _generate_token()
        raw_code = _generate_code()
        challenge = PasswordResetChallenge.objects.create(
            user=user,
            token_hash=_pepper_hash(raw_token),
            code_hash=_pepper_hash(_normalize_code(raw_code)),
            portal=portal_resolved,
            request_ip=ip,
            user_agent=ua,
            expires_at=timezone.now() + timedelta(minutes=TTL_MINUTES),
        )
        sent = _send_reset_email(
            user=user,
            raw_token=raw_token,
            raw_code=raw_code,
            portal=portal_resolved,
            request=request,
        )
        if not sent:
            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=["consumed_at"])
            # Toujours message générique — pas de fuite « e-mail KO »
        try:
            AuditLog.objects.create(
                actor=user,
                action=AuditLog.Action.SYSTEM,
                resource_type="password_reset_challenge",
                resource_id=str(challenge.pk),
                message="Demande mot de passe oublié (e-mail)",
                ip_address=ip,
                user_agent=ua,
                request_id=getattr(request, "request_id", "") if request else "",
                metadata={"portal": portal_resolved, "email_sent": bool(sent)},
            )
        except Exception:  # noqa: BLE001
            pass

    # Uniformise le temps de réponse pour réduire les oracles timing (sauf tests)
    if not getattr(settings, "TESTING", False):
        elapsed = time.monotonic() - started
        target = 0.35
        if elapsed < target:
            time.sleep(target - elapsed)

    return {"detail": GENERIC_REQUEST_MSG}


@transaction.atomic
def confirm_password_reset(
    *,
    token: str,
    code: str,
    new_password: str,
    request=None,
) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Valide token + code e-mail, pose le nouveau MDP, révoque les sessions."""
    if not _forgot_enabled():
        raise VZoneAPIException(
            detail="La réinitialisation par e-mail est désactivée.",
            code="forgot_password_disabled",
            status_code=403,
        )

    ip, ua = _client_meta(request)
    if ip:
        _cache_bump(f"fp:cfm:ip:{ip}", CONFIRM_IP_LIMIT, CONFIRM_IP_WINDOW)

    raw_token = (token or "").strip()
    norm_code = _normalize_code(code)
    if not raw_token or len(raw_token) < 20 or len(norm_code) != CODE_LENGTH:
        raise VZoneAPIException(
            detail="Lien ou code de vérification invalide.",
            code="forgot_password_invalid",
            status_code=400,
        )

    token_hash = _pepper_hash(raw_token)
    challenge = (
        PasswordResetChallenge.objects.select_for_update()
        .select_related("user")
        .filter(token_hash=token_hash)
        .first()
    )
    if challenge is None:
        raise VZoneAPIException(
            detail="Lien ou code de vérification invalide.",
            code="forgot_password_invalid",
            status_code=400,
        )

    now = timezone.now()
    if challenge.consumed_at is not None:
        raise VZoneAPIException(
            detail="Ce lien a déjà été utilisé. Refaites une demande.",
            code="forgot_password_consumed",
            status_code=400,
        )
    if challenge.expires_at <= now:
        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at"])
        raise VZoneAPIException(
            detail="Ce lien a expiré. Refaites une demande.",
            code="forgot_password_expired",
            status_code=400,
        )

    expected_code = challenge.code_hash
    provided_code = _pepper_hash(norm_code)
    if not hmac.compare_digest(expected_code, provided_code):
        challenge.attempts = int(challenge.attempts or 0) + 1
        fields = ["attempts"]
        if challenge.attempts >= MAX_CODE_ATTEMPTS:
            challenge.consumed_at = now
            fields.append("consumed_at")
        challenge.save(update_fields=fields)
        raise VZoneAPIException(
            detail="Code de vérification incorrect.",
            code="forgot_password_bad_code",
            status_code=400,
            extra={"attempts_left": max(0, MAX_CODE_ATTEMPTS - challenge.attempts)},
        )

    user = challenge.user
    if not user.is_active or user.is_suspended:
        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at"])
        raise VZoneAPIException(
            detail="Compte indisponible.",
            code="forgot_password_account",
            status_code=403,
        )

    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        raise VZoneAPIException(
            detail="; ".join(exc.messages) if exc.messages else "Mot de passe invalide.",
            code="password_invalid",
            status_code=400,
        ) from exc
    try:
        from apps.security.services import validate_password_against_policy

        validate_password_against_policy(new_password)
    except ImportError:
        pass

    user.set_password(new_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password", "updated_at"])

    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at"])
    PasswordResetChallenge.objects.filter(
        user=user, consumed_at__isnull=True
    ).exclude(pk=challenge.pk).update(consumed_at=now)

    try:
        from apps.accounts.password_reset import revoke_all_user_sessions

        revoke_all_user_sessions(user)
    except Exception:  # noqa: BLE001
        logger.debug("forgot-password revoke sessions failed", exc_info=True)

    try:
        from apps.security.services import clear_lockouts

        clear_lockouts(email=user.email, ip=ip)
    except Exception:  # noqa: BLE001
        pass

    try:
        AuditLog.objects.create(
            actor=user,
            action=AuditLog.Action.UPDATE,
            resource_type="user",
            resource_id=str(user.pk),
            message="Mot de passe réinitialisé via e-mail (forgot-password)",
            ip_address=ip,
            user_agent=ua,
            request_id=getattr(request, "request_id", "") if request else "",
            metadata={"challenge_id": challenge.pk},
        )
    except Exception:  # noqa: BLE001
        pass

    try:
        from apps.server_setup.contact_notify import notify_password_reset

        notify_password_reset(user, actor=user, request=request)
    except Exception:  # noqa: BLE001
        pass

    return {
        "detail": "Mot de passe mis à jour. Connectez-vous avec le nouveau mot de passe.",
        "username": user.username,
    }
