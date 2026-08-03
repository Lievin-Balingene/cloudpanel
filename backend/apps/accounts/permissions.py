"""Permissions spécifiques au module accounts."""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.accounts.models import User


class CanManageUsers(BasePermission):
    message = "Gestion des utilisateurs non autorisée."

    def has_permission(self, request, view) -> bool:  # type: ignore[no-untyped-def]
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == User.Role.ADMINISTRATOR:
            return True
        if user.role == User.Role.RESELLER:
            return True
        return user.has_module_perm("accounts.manage_user")
