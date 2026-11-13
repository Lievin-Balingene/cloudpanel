"""Réinitialisation sécurisée du mot de passe d'un compte (WHM).

- Mot de passe généré côté serveur (jamais choisi par l'admin dans ce flux)
- must_change_password forcé au prochain login
- Révocation de toutes les sessions / refresh JWT
- Confirmation username obligatoire
- Audit + notice Contact Manager sans plaintext
"""
from __future__ import annotations

import logging
import secrets
import string
from typing import Any

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.accounts.models import User, UserSession
from apps.core.exceptions import VZoneAPIException
from apps.core.models import AuditLog

logger = logging.getLogger(__name__)

# Alphabet sans caractères ambigus (O/0, I/l/1) pour lecture orale / copie
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%&*-_=+"


def generate_secure_password(length: int | None = None) -> str:
    """Génère un mot de passe conforme à la politique sécurité."""
    from apps.security.services import get_policy, validate_password_against_policy

    policy = get_policy()
    target_len = max(int(length or 20), int(policy.password_min_length or 10), 16)

    for _ in range(64):
        chars = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%&*-_=+"),
        ]
        chars += [secrets.choice(_ALPHABET) for _ in range(target_len - len(chars))]
        # Fisher–Yates via secrets
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        password = "".join(chars)
        try:
            validate_password_against_policy(password)
            validate_password(password)
            return password
        except (VZoneAPIException, ValidationError):
            continue

    raise VZoneAPIException(
        detail="Impossible de générer un mot de passe conforme à la politique.",
        code="password_generate_failed",
        status_code=500,
    )


def revoke_all_user_sessions(user: User) -> int:
    """Révoque sessions panel + blacklist tous les refresh JWT outstanding."""
    revoked = UserSession.objects.filter(user=user, is_revoked=False).update(is_revoked=True)
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        for token in OutstandingToken.objects.filter(user_id=user.pk):
            BlacklistedToken.objects.get_or_create(token=token)
    except Exception:  # noqa: BLE001
        logger.debug("JWT blacklist skip for user=%s", user.username, exc_info=True)
    return int(revoked)


def assert_can_reset_password(*, actor: User, target: User) -> None:
    if target.pk == actor.pk:
        raise VZoneAPIException(
            detail="Impossible de réinitialiser votre propre mot de passe via cet outil.",
            code="password_reset_self",
            status_code=400,
        )
    if target.role == User.Role.ADMINISTRATOR:
        raise VZoneAPIException(
            detail="Réinitialisation interdite sur un compte administrateur.",
            code="password_reset_forbidden",
            status_code=403,
        )
    if actor.role == User.Role.RESELLER:
        if target.parent_id != actor.id:
            raise VZoneAPIException(
                detail="Ce compte n'appartient pas à votre reseller.",
                code="password_reset_forbidden",
                status_code=403,
            )
        if not actor.has_reseller_priv("edit-account"):
            raise VZoneAPIException(
                detail="Privilege edit-account requis.",
                code="reseller_privilege_denied",
                status_code=403,
            )
    elif actor.role != User.Role.ADMINISTRATOR:
        raise VZoneAPIException(
            detail="Action réservée aux administrateurs / revendeurs.",
            code="forbidden",
            status_code=403,
        )
    if target.role not in {User.Role.CLIENT, User.Role.RESELLER}:
        raise VZoneAPIException(
            detail="Réinitialisation disponible uniquement pour client / revendeur.",
            code="password_reset_forbidden",
            status_code=400,
        )


def reset_account_password(
    *,
    actor: User,
    target: User,
    confirm_username: str,
    request=None,  # type: ignore[no-untyped-def]
) -> dict[str, Any]:
    """Réinitialise le mot de passe de façon sécurisée. Retourne le mdp une seule fois."""
    assert_can_reset_password(actor=actor, target=target)

    expected = (target.username or "").strip()
    provided = (confirm_username or "").strip()
    # compare_digest exige la même longueur ; mismatch de taille = rejet
    if (
        not provided
        or len(provided) != len(expected)
        or not secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))
    ):
        raise VZoneAPIException(
            detail="Confirmation username incorrecte. Saisissez le nom d'utilisateur exact.",
            code="password_reset_confirm_mismatch",
            status_code=400,
        )

    temporary = generate_secure_password()
    target.set_password(temporary)
    target.must_change_password = True
    target.save(update_fields=["password", "must_change_password", "updated_at"])

    sessions_revoked = revoke_all_user_sessions(target)

    ip = None
    ua = ""
    if request is not None:
        try:
            from apps.security.services import client_ip

            ip = client_ip(request)
        except Exception:  # noqa: BLE001
            ip = request.META.get("REMOTE_ADDR")
        ua = (request.META.get("HTTP_USER_AGENT") or "")[:512]

    AuditLog.objects.create(
        actor=actor,
        action=AuditLog.Action.UPDATE,
        resource_type="user",
        resource_id=str(target.pk),
        message=f"Password reset for {target.username} (force change, sessions revoked)",
        ip_address=ip,
        user_agent=ua,
        request_id=getattr(request, "request_id", "") or "",
        metadata={
            "must_change_password": True,
            "sessions_revoked": sessions_revoked,
            "target_username": target.username,
        },
    )

    try:
        from apps.server_setup.contact_notify import notify_password_reset

        notify_password_reset(target, actor=actor, request=request)
    except Exception:  # noqa: BLE001
        logger.debug("password reset notify failed", exc_info=True)

    logger.info(
        "WHM password reset: actor=%s target=%s sessions_revoked=%s",
        actor.username,
        target.username,
        sessions_revoked,
    )

    return {
        "user_id": target.pk,
        "username": target.username,
        "temporary_password": temporary,
        "must_change_password": True,
        "sessions_revoked": sessions_revoked,
        "shown_once": True,
        "message": (
            "Mot de passe temporaire généré. Affiché une seule fois — "
            "l'utilisateur devra le changer à la prochaine connexion."
        ),
    }
