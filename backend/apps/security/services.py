"""Services sécurité panel : politique, IP, lockout."""
from __future__ import annotations

import ipaddress
import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException
from apps.security.models import AccountLockout, IpAccessRule, LoginAttempt, SecurityPolicy


def get_policy() -> SecurityPolicy:
    policy = SecurityPolicy.objects.order_by("pk").first()
    if policy is None:
        policy = SecurityPolicy.objects.create()
    return policy


@transaction.atomic
def update_policy(**fields: Any) -> SecurityPolicy:
    policy = get_policy()
    allowed = {
        "password_min_length",
        "require_uppercase",
        "require_digit",
        "require_special",
        "lockout_max_attempts",
        "lockout_window_minutes",
        "lockout_duration_minutes",
        "ip_mode",
        "force_2fa_admins",
    }
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        if key == "ip_mode" and value not in SecurityPolicy.IpMode.values:
            raise VZoneAPIException(detail="Mode IP invalide.", code="invalid_ip_mode", status_code=400)
        if key in {
            "password_min_length",
            "lockout_max_attempts",
            "lockout_window_minutes",
            "lockout_duration_minutes",
        }:
            value = max(1, int(value))
        setattr(policy, key, value)
    policy.save()
    return policy


def client_ip(request) -> str | None:  # type: ignore[no-untyped-def]
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR") if request else None
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request:
        return request.META.get("REMOTE_ADDR")
    return None


def _ip_in_cidr(ip: str, cidr: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def assert_ip_allowed(ip: str | None) -> None:
    policy = get_policy()
    if policy.ip_mode == SecurityPolicy.IpMode.OFF:
        return
    if not ip:
        raise VZoneAPIException(
            detail="Adresse IP introuvable — accès refusé.",
            code="ip_forbidden",
            status_code=403,
        )
    rules = IpAccessRule.objects.filter(is_active=True)
    if policy.ip_mode == SecurityPolicy.IpMode.ALLOWLIST:
        allows = rules.filter(list_type=IpAccessRule.ListType.ALLOW)
        if not allows.exists():
            return
        if not any(_ip_in_cidr(ip, r.cidr) for r in allows):
            raise VZoneAPIException(
                detail="Adresse IP non autorisée.",
                code="ip_forbidden",
                status_code=403,
            )
        return
    # blocklist
    blocks = rules.filter(list_type=IpAccessRule.ListType.BLOCK)
    if any(_ip_in_cidr(ip, r.cidr) for r in blocks):
        raise VZoneAPIException(
            detail="Adresse IP bloquée.",
            code="ip_forbidden",
            status_code=403,
        )


def _lock_key_email(email: str) -> str:
    return f"email:{email.lower().strip()}"


def _lock_key_ip(ip: str) -> str:
    return f"ip:{ip}"


def assert_not_locked(*, email: str, ip: str | None) -> None:
    now = timezone.now()
    keys = [_lock_key_email(email)]
    if ip:
        keys.append(_lock_key_ip(ip))
    for key in keys:
        lock = AccountLockout.objects.filter(key=key).first()
        if lock and lock.locked_until and lock.locked_until > now:
            raise VZoneAPIException(
                detail="Compte temporairement verrouillé après trop d'échecs.",
                code="locked_out",
                status_code=403,
                extra={"locked_until": lock.locked_until.isoformat()},
            )


def record_login_attempt(
    *,
    email: str,
    ip: str | None,
    success: bool,
    message: str = "",
) -> None:
    LoginAttempt.objects.create(
        email=(email or "")[:254],
        ip_address=ip,
        success=success,
        message=message[:255],
    )
    if success:
        clear_lockouts(email=email, ip=ip)
        return

    policy = get_policy()
    now = timezone.now()
    window = now - timedelta(minutes=policy.lockout_window_minutes)
    keys = [_lock_key_email(email)]
    if ip:
        keys.append(_lock_key_ip(ip))

    for key in keys:
        if key.startswith("email:"):
            fails = LoginAttempt.objects.filter(
                email__iexact=email, success=False, created_at__gte=window
            ).count()
        else:
            fails = LoginAttempt.objects.filter(
                ip_address=ip, success=False, created_at__gte=window
            ).count()
        lock, _ = AccountLockout.objects.get_or_create(key=key)
        lock.attempts = fails
        if fails >= policy.lockout_max_attempts:
            lock.locked_until = now + timedelta(minutes=policy.lockout_duration_minutes)
        lock.save()


def clear_lockouts(*, email: str, ip: str | None) -> None:
    keys = [_lock_key_email(email)]
    if ip:
        keys.append(_lock_key_ip(ip))
    AccountLockout.objects.filter(key__in=keys).delete()


def validate_password_against_policy(password: str) -> None:
    policy = get_policy()
    if len(password) < policy.password_min_length:
        raise VZoneAPIException(
            detail=f"Le mot de passe doit contenir au moins {policy.password_min_length} caractères.",
            code="password_policy",
            status_code=400,
        )
    if policy.require_uppercase and not re.search(r"[A-Z]", password):
        raise VZoneAPIException(
            detail="Le mot de passe doit contenir une majuscule.",
            code="password_policy",
            status_code=400,
        )
    if policy.require_digit and not re.search(r"\d", password):
        raise VZoneAPIException(
            detail="Le mot de passe doit contenir un chiffre.",
            code="password_policy",
            status_code=400,
        )
    if policy.require_special and not re.search(r"[^A-Za-z0-9]", password):
        raise VZoneAPIException(
            detail="Le mot de passe doit contenir un caractère spécial.",
            code="password_policy",
            status_code=400,
        )


def assert_admin_2fa_if_required(user: User) -> None:
    policy = get_policy()
    if not policy.force_2fa_admins:
        return
    if user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER} and not user.two_factor_enabled:
        raise VZoneAPIException(
            detail="La 2FA est obligatoire pour ce rôle. Activez-la avant de vous connecter.",
            code="two_factor_required",
            status_code=403,
        )


@transaction.atomic
def create_ip_rule(
    *,
    cidr: str,
    list_type: str,
    notes: str = "",
    is_active: bool = True,
    created_by: User | None = None,
) -> IpAccessRule:
    cidr = (cidr or "").strip()
    try:
        ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise VZoneAPIException(detail="CIDR invalide.", code="invalid_cidr", status_code=400) from exc
    if list_type not in IpAccessRule.ListType.values:
        raise VZoneAPIException(detail="Type de liste invalide.", code="invalid_list_type", status_code=400)
    return IpAccessRule.objects.create(
        cidr=cidr,
        list_type=list_type,
        notes=notes,
        is_active=is_active,
        created_by=created_by,
    )


def delete_ip_rule(rule: IpAccessRule) -> None:
    rule.delete()


def unlock_key(key: str) -> bool:
    deleted, _ = AccountLockout.objects.filter(key=key).delete()
    return deleted > 0


def overview_for(_user: User | None = None) -> dict[str, Any]:
    policy = get_policy()
    now = timezone.now()
    since = now - timedelta(hours=24)
    return {
        "policy": {
            "password_min_length": policy.password_min_length,
            "require_uppercase": policy.require_uppercase,
            "require_digit": policy.require_digit,
            "require_special": policy.require_special,
            "lockout_max_attempts": policy.lockout_max_attempts,
            "lockout_window_minutes": policy.lockout_window_minutes,
            "lockout_duration_minutes": policy.lockout_duration_minutes,
            "ip_mode": policy.ip_mode,
            "force_2fa_admins": policy.force_2fa_admins,
        },
        "users_total": User.objects.count(),
        "users_2fa_enabled": User.objects.filter(two_factor_enabled=True).count(),
        "users_must_change_password": User.objects.filter(must_change_password=True).count(),
        "ip_rules": IpAccessRule.objects.filter(is_active=True).count(),
        "lockouts_active": AccountLockout.objects.filter(locked_until__gt=now).count(),
        "login_failures_24h": LoginAttempt.objects.filter(success=False, created_at__gte=since).count(),
        "login_success_24h": LoginAttempt.objects.filter(success=True, created_at__gte=since).count(),
    }


def my_security_status(user: User) -> dict[str, Any]:
    policy = get_policy()
    return {
        "two_factor_enabled": user.two_factor_enabled,
        "must_change_password": user.must_change_password,
        "force_2fa_admins": policy.force_2fa_admins,
        "password_min_length": policy.password_min_length,
        "require_uppercase": policy.require_uppercase,
        "require_digit": policy.require_digit,
        "require_special": policy.require_special,
    }
