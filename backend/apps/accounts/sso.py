"""SSO WHM → panneau client (Login as) — style cPanel, one-time handoff."""
from __future__ import annotations

import logging
import secrets
from typing import Any

from django.core.cache import cache

from apps.accounts.models import User
from apps.accounts.services import issue_tokens
from apps.core.exceptions import VZoneAPIException

logger = logging.getLogger(__name__)

HANDOFF_TTL = 60  # secondes
HANDOFF_PREFIX = "whm_login_as:"


def create_login_as_handoff(
    *,
    actor: User,
    target: User,
    request=None,  # type: ignore[no-untyped-def]
) -> dict[str, Any]:
    """Crée un jeton one-shot pour ouvrir le panneau client en tant que `target`."""
    if target.role == User.Role.ADMINISTRATOR:
        raise VZoneAPIException(
            detail="Impossible de se connecter en tant qu'administrateur.",
            code="login_as_forbidden",
            status_code=403,
        )
    if actor.role == User.Role.RESELLER:
        if target.parent_id != actor.id:
            raise VZoneAPIException(
                detail="Ce compte n'appartient pas à votre reseller.",
                code="login_as_forbidden",
                status_code=403,
            )
        if not actor.has_reseller_priv("list-accts"):
            raise VZoneAPIException(
                detail="Privilege list-accts requis.",
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
            detail="Login as disponible uniquement pour client / revendeur.",
            code="login_as_forbidden",
            status_code=400,
        )

    tokens = issue_tokens(target, request=request)
    token = secrets.token_urlsafe(32)
    payload = {
        "tokens": tokens,
        "user_id": target.pk,
        "actor_id": actor.pk,
        "username": target.username,
    }
    cache.set(f"{HANDOFF_PREFIX}{token}", payload, timeout=HANDOFF_TTL)
    logger.info(
        "WHM login-as handoff: actor=%s target=%s",
        actor.username,
        target.username,
    )
    return {
        "handoff": token,
        "expires_in": HANDOFF_TTL,
        "username": target.username,
        "user_id": target.pk,
    }


def consume_login_as_handoff(token: str) -> dict[str, Any]:
    """Échange le jeton one-shot contre tokens JWT (supprimé immédiatement)."""
    key = f"{HANDOFF_PREFIX}{(token or '').strip()}"
    payload = cache.get(key)
    if not payload or not isinstance(payload, dict):
        raise VZoneAPIException(
            detail="Lien de connexion expiré ou invalide. Réessayez depuis WHM.",
            code="sso_invalid",
            status_code=400,
        )
    cache.delete(key)
    user = User.objects.filter(pk=payload.get("user_id")).first()
    if not user or not user.is_active:
        raise VZoneAPIException(
            detail="Compte cible indisponible.",
            code="sso_user_unavailable",
            status_code=400,
        )
    from apps.accounts.serializers import MeSerializer

    return {
        "tokens": payload["tokens"],
        "user": MeSerializer(user).data,
        "actor_id": payload.get("actor_id"),
        "login_as": True,
    }
