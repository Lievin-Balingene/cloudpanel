"""Services ACL revendeur + isolation proprietaire."""
from __future__ import annotations

from django.db import transaction

from apps.accounts.models import ResellerPrivileges, User
from apps.accounts.reseller_acl import (
    default_privileges_for_package,
    sanitize_privileges,
)
from apps.core.exceptions import VZoneAPIException


def ensure_reseller_privileges(
    user: User,
    *,
    privileges: list[str] | None = None,
    can_create_packages: bool = True,
    updated_by: User | None = None,
) -> ResellerPrivileges:
    """Cree ou met a jour l'ACL d'un compte revendeur."""
    if user.role != User.Role.RESELLER:
        raise VZoneAPIException(
            detail="Les privileges revendeur ne s'appliquent qu'aux comptes revendeur.",
            code="invalid_role",
            status_code=400,
        )
    codes = sanitize_privileges(
        privileges
        if privileges is not None
        else default_privileges_for_package(can_create_packages=can_create_packages)
    )
    acl, created = ResellerPrivileges.objects.get_or_create(
        user=user,
        defaults={
            "privileges": codes,
            "updated_by": updated_by,
        },
    )
    if not created and privileges is not None:
        acl.privileges = codes
        acl.updated_by = updated_by
        acl.save(update_fields=["privileges", "updated_by", "updated_at"])
    return acl


def get_reseller_privilege_codes(user: User) -> list[str]:
    if user.is_administrator:
        from apps.accounts.reseller_acl import ALL_PRIVILEGE_CODES

        return sorted(ALL_PRIVILEGE_CODES)
    if not user.is_reseller:
        return []
    acl = ResellerPrivileges.objects.filter(user=user).first()
    if acl:
        return list(acl.privileges or [])
    return default_privileges_for_package()


def assert_reseller_priv(user: User, code: str) -> None:
    if user.is_administrator:
        return
    if not user.has_reseller_priv(code):
        raise VZoneAPIException(
            detail=f"Privilege revendeur requis : {code}.",
            code="reseller_privilege_denied",
            status_code=403,
            extra={"privilege": code},
        )


def assert_owns_account(actor: User, target: User) -> None:
    """Securite : un revendeur ne touche que ses clients (parent=soi)."""
    if actor.is_administrator:
        return
    if actor.is_reseller:
        if target.parent_id != actor.pk:
            raise VZoneAPIException(
                detail="Ce compte n'appartient pas a votre organisation revendeur.",
                code="ownership_denied",
                status_code=403,
            )
        return
    raise VZoneAPIException(
        detail="Action non autorisee.",
        code="forbidden",
        status_code=403,
    )


@transaction.atomic
def sync_privileges_from_package(user: User, *, can_create_packages: bool) -> None:
    """A l'assignation d'un package revendeur : complete l'ACL sans retirer les droits root deja accordes."""
    if user.role != User.Role.RESELLER:
        return
    acl = ResellerPrivileges.objects.filter(user=user).first()
    base = set(default_privileges_for_package(can_create_packages=can_create_packages))
    if acl:
        current = set(acl.privileges or [])
        # On ajoute les manquants du package, on ne retire pas les privileges admin deja donnes
        merged = sanitize_privileges(current | base)
        acl.privileges = merged
        acl.save(update_fields=["privileges", "updated_at"])
    else:
        ensure_reseller_privileges(user, can_create_packages=can_create_packages)
