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
    Port Admin  → administrator | reseller (WHM) — uniquement :9086.
    Port Client → client | reseller — :9082 et hostname :80/:443.
    shared      → traité comme client (plus de contournement WHM).
    Sinon → 403 wrong_portal.
    """
    portal = (portal or "").strip().lower()
    # Ancien mode shared (:80/:443) = client only — WHM forcé sur :9086
    if portal == "shared":
        portal = "client"
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

    # Style cPanel : le revendeur se connecte aussi sur le port Client (son cPanel).
    # L'administrateur root reste sur le port Admin uniquement.
    if portal == "client" and role == User.Role.ADMINISTRATOR:
        raise VZoneAPIException(
            detail=(
                "Authentification refusée : le port Client n’accepte pas le compte "
                "administrateur. Connectez-vous sur le port Admin (WHM)."
            ),
            code="wrong_portal",
            status_code=403,
        )
