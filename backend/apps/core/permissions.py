"""Permissions granulaires de base."""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsAdministrator(BasePermission):
    """Accès réservé aux administrateurs système."""

    message = "Droits administrateur requis."

    def has_permission(self, request, view) -> bool:  # type: ignore[no-untyped-def]
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "role", None) == "administrator"
        )


class IsResellerOrAdmin(BasePermission):
    message = "Droits revendeur ou administrateur requis."

    def has_permission(self, request, view) -> bool:  # type: ignore[no-untyped-def]
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "role", None) in {"administrator", "reseller"}
        )


class HasModulePermission(BasePermission):
    """Vérifie une permission module explicite sur l'utilisateur."""

    def __init__(self, permission_codename: str) -> None:
        self.permission_codename = permission_codename

    def has_permission(self, request, view) -> bool:  # type: ignore[no-untyped-def]
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "role", None) == "administrator":
            return True
        perms = getattr(user, "module_permissions", None)
        if perms is None:
            return False
        return self.permission_codename in perms


class HasResellerPrivilege(BasePermission):
    """
    Privilege ACL revendeur (style cPanel).
    Sur la vue : `reseller_privilege = "create-acct"` ou `reseller_privileges = [...]`.
    """

    message = "Privilege revendeur insuffisant."

    def has_permission(self, request, view) -> bool:  # type: ignore[no-untyped-def]
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "role", None) == "administrator":
            return True
        if getattr(user, "role", None) != "reseller":
            return False
        codes = getattr(view, "reseller_privileges", None)
        if codes is None:
            single = getattr(view, "reseller_privilege", None)
            codes = [single] if single else []
        if not codes:
            return True
        return any(user.has_reseller_priv(c) for c in codes if c)
