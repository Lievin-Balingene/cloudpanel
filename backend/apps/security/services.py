"""Services sécurité panel : politique, IP, lockout."""
from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import os
import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException
from apps.files.services import personal_home, user_home
from apps.security.models import AccountLockout, IpAccessRule, LoginAttempt, SecurityPolicy

SSH_KEY_TYPE_RE = re.compile(
    r"^(?:ssh-(?:rsa|dss|ed25519)|ecdsa-sha2-nistp(?:256|384|521)|"
    r"sk-(?:ssh-ed25519|ecdsa-sha2-nistp256)@openssh\.com)$"
)


def _authorized_keys_path(user: User):
    user_home(user)
    ssh_dir = personal_home(user) / ".ssh"
    try:
        ssh_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(ssh_dir, 0o700)
    except OSError as exc:
        raise VZoneAPIException(
            detail=f"Répertoire SSH inaccessible: {exc}",
            code="ssh_unavailable",
            status_code=500,
        ) from exc
    return ssh_dir / "authorized_keys"


def _parse_ssh_key_line(line: str, index: int) -> dict | None:
    parts = line.strip().split()
    key_pos = next(
        (pos for pos, value in enumerate(parts) if SSH_KEY_TYPE_RE.fullmatch(value)),
        None,
    )
    if key_pos is None or key_pos + 1 >= len(parts):
        return None
    key_type = parts[key_pos]
    encoded = parts[key_pos + 1]
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError, binascii.Error):
        return None
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
    name = " ".join(parts[key_pos + 2 :])
    return {
        "id": index,
        "index": index,
        "name": name,
        "key_type": key_type,
        "public_key": f"{key_type} {encoded}",
        "fingerprint": fingerprint,
    }


def list_ssh_keys(user: User) -> list[dict]:
    path = _authorized_keys_path(user)
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise VZoneAPIException(
            detail=f"Lecture des clés SSH impossible: {exc}",
            code="ssh_read_error",
            status_code=500,
        ) from exc
    return [
        parsed
        for index, line in enumerate(lines)
        if (parsed := _parse_ssh_key_line(line, index)) is not None
    ]


def add_ssh_key(user: User, name: str, public_key: str) -> dict:
    parsed = _parse_ssh_key_line((public_key or "").strip(), 0)
    if parsed is None:
        raise VZoneAPIException(
            detail="Clé publique SSH invalide.",
            code="invalid_ssh_key",
            status_code=400,
        )
    clean_name = " ".join((name or parsed["name"] or "").split())
    if "\n" in clean_name or "\r" in clean_name or len(clean_name) > 255:
        raise VZoneAPIException(
            detail="Nom de clé SSH invalide.",
            code="invalid_key_name",
            status_code=400,
        )
    if any(item["fingerprint"] == parsed["fingerprint"] for item in list_ssh_keys(user)):
        raise VZoneAPIException(
            detail="Cette clé SSH est déjà enregistrée.",
            code="ssh_key_exists",
            status_code=400,
        )

    path = _authorized_keys_path(user)
    line = parsed["public_key"] + (f" {clean_name}" if clean_name else "")
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        content = existing.rstrip("\n")
        path.write_text(f"{content}\n{line}\n" if content else f"{line}\n", encoding="utf-8")
        os.chmod(path, 0o600)
    except OSError as exc:
        raise VZoneAPIException(
            detail=f"Écriture de la clé SSH impossible: {exc}",
            code="ssh_write_error",
            status_code=500,
        ) from exc
    keys = list_ssh_keys(user)
    return next(item for item in keys if item["fingerprint"] == parsed["fingerprint"])


def delete_ssh_key(user: User, fingerprint_or_index: str | int) -> None:
    path = _authorized_keys_path(user)
    if not path.is_file():
        raise VZoneAPIException(
            detail="Clé SSH introuvable.",
            code="ssh_key_not_found",
            status_code=404,
        )
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise VZoneAPIException(
            detail=f"Lecture des clés SSH impossible: {exc}",
            code="ssh_read_error",
            status_code=500,
        ) from exc

    target_index: int | None = None
    if isinstance(fingerprint_or_index, int):
        target_index = fingerprint_or_index
    else:
        for item in list_ssh_keys(user):
            if item["fingerprint"] == fingerprint_or_index:
                target_index = item["index"]
                break
    if target_index is None or target_index < 0 or target_index >= len(lines):
        raise VZoneAPIException(
            detail="Clé SSH introuvable.",
            code="ssh_key_not_found",
            status_code=404,
        )
    if _parse_ssh_key_line(lines[target_index], target_index) is None:
        raise VZoneAPIException(
            detail="Clé SSH introuvable.",
            code="ssh_key_not_found",
            status_code=404,
        )
    del lines[target_index]
    try:
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        os.chmod(path, 0o600)
    except OSError as exc:
        raise VZoneAPIException(
            detail=f"Suppression de la clé SSH impossible: {exc}",
            code="ssh_write_error",
            status_code=500,
        ) from exc


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
    """
    IP client pour lockout / allowlist.
    Derrière nginx local : X-Real-IP (écrasé par le proxy) — pas spoofable de l'extérieur.
    Connexion directe : REMOTE_ADDR uniquement.
    """
    if not request:
        return None
    remote = (request.META.get("REMOTE_ADDR") or "").strip() or None
    if remote in {"127.0.0.1", "::1"}:
        real = (request.META.get("HTTP_X_REAL_IP") or "").strip()
        if real:
            return real
        if bool(getattr(settings, "VZONE_TRUST_X_FORWARDED_FOR", False)):
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            if forwarded:
                return forwarded.split(",")[0].strip() or None
    return remote


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
