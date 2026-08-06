"""Isolation portail Admin (:9086) / Client (:9082) via en-tête nginx X-Vzone-Portal."""
from __future__ import annotations

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException


def request_portal(request) -> str:  # type: ignore[no-untyped-def]
    if request is None:
        return ""
    return (
        request.META.get("HTTP_X_VZONE_PORTAL")
        or getattr(request, "headers", {}).get("X-Vzone-Portal")
        or ""
    ).strip().lower()


def assert_role_allowed_on_portal(user: User, portal: str) -> None:
    """
    Port Admin  → administrator | reseller uniquement.
    Port Client → client uniquement.
    Sinon → 403 wrong_portal (rejette l'auth / l'accès API).
    shared / vide → pas de filtre (hostname :80/:443).
    """
    portal = (portal or "").strip().lower()
    if portal not in {"admin", "client", "webmail"}:
        return

    role = getattr(user, "role", None)

    if portal == "webmail":
        raise VZoneAPIException(
            detail="Ce port est réservé au webmail. Utilisez le port Admin ou Client.",
            code="wrong_portal",
            status_code=403,
        )

    if portal == "admin" and role == User.Role.CLIENT:
        raise VZoneAPIException(
            detail=(
                "Authentification refusée : le port Admin n’accepte que les comptes "
                "administrateur ou revendeur. Connectez-vous sur le port Client."
            ),
            code="wrong_portal",
            status_code=403,
        )

    if portal == "client" and role in {
        User.Role.ADMINISTRATOR,
        User.Role.RESELLER,
    }:
        raise VZoneAPIException(
            detail=(
                "Authentification refusée : le port Client n’accepte que les comptes "
                "d’hébergement. Connectez-vous sur le port Admin."
            ),
            code="wrong_portal",
            status_code=403,
        )
