"""Services ACL revendeur + isolation proprietaire + limite de comptes."""
from __future__ import annotations

from django.db import transaction

from apps.accounts.models import ResellerPrivileges, User
from apps.accounts.reseller_acl import (
    default_privileges_for_package,
    sanitize_privileges,
)
from apps.core.exceptions import QuotaExceeded, VZoneAPIException


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


def count_reseller_client_accounts(reseller: User) -> int:
    return User.objects.filter(parent=reseller, role=User.Role.CLIENT).count()


def _package_max_accounts(reseller: User) -> int | None:
    """Limite héritée du package. None = pas de package ; 0 = illimité."""
    try:
        from apps.packages.models import PackageAssignment

        assignment = (
            PackageAssignment.objects.filter(user=reseller)
            .select_related("package")
            .first()
        )
        if assignment and assignment.package_id:
            return int(assignment.package.max_accounts or 0)
    except Exception:  # noqa: BLE001
        return None
    return None


def _global_tweak_max_accounts() -> int:
    """Plafond global Tweak Settings (0 = pas de plafond global)."""
    try:
        from apps.server_setup.models import ServerSetup
        from apps.server_setup.tweak_settings import merge_tweaks

        setup = ServerSetup.get_solo()
        values = merge_tweaks(setup.tweak_settings)
        return int(values.get("max_accounts_per_reseller") or 0)
    except Exception:  # noqa: BLE001
        return 0


def resolve_reseller_account_limit(reseller: User) -> dict:
    """
    Limite effective de comptes clients.

    Priorité :
    1. ACL max_accounts si non null (0 = illimité)
    2. sinon package.max_accounts (0 = illimité)
    3. plafond global Tweak Settings si > 0
    """
    used = count_reseller_client_accounts(reseller)
    acl = ResellerPrivileges.objects.filter(user=reseller).first()
    acl_limit = getattr(acl, "max_accounts", None) if acl else None
    pkg_limit = _package_max_accounts(reseller)
    global_cap = _global_tweak_max_accounts()

    source = "unlimited"
    effective: int | None = None

    if acl_limit is not None:
        source = "acl"
        effective = None if int(acl_limit) == 0 else int(acl_limit)
    elif pkg_limit is not None:
        source = "package"
        effective = None if int(pkg_limit) == 0 else int(pkg_limit)

    if global_cap > 0:
        if effective is None:
            effective = global_cap
            if source == "unlimited":
                source = "tweak"
        else:
            effective = min(effective, global_cap)

    remaining = None if effective is None else max(0, effective - used)
    return {
        "unlimited": effective is None,
        "max_accounts": effective,
        "used_accounts": used,
        "remaining": remaining,
        "source": source,
        "acl_max_accounts": acl_limit,
        "package_max_accounts": pkg_limit,
        "global_max_accounts": global_cap or None,
    }


def assert_reseller_can_create_account(reseller: User) -> dict:
    """Lève QuotaExceeded si le plafond de comptes est atteint."""
    if not reseller.is_reseller:
        return {"unlimited": True, "used_accounts": 0}
    info = resolve_reseller_account_limit(reseller)
    if info["unlimited"]:
        return info
    max_n = int(info["max_accounts"] or 0)
    used = int(info["used_accounts"] or 0)
    if used >= max_n:
        raise QuotaExceeded(
            detail=(
                f"Limite de comptes atteinte ({used}/{max_n}). "
                "Demandez à l’administrateur d’augmenter le plafond ou de passer en illimité."
            ),
            extra=info,
        )
    return info


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
    """Complete l'ACL depuis le package sans retirer les droits déjà accordés."""
    if user.role != User.Role.RESELLER:
        return
    acl = ResellerPrivileges.objects.filter(user=user).first()
    base = set(default_privileges_for_package(can_create_packages=can_create_packages))
    if acl:
        current = set(acl.privileges or [])
        merged = sanitize_privileges(current | base)
        acl.privileges = merged
        acl.save(update_fields=["privileges", "updated_at"])
    else:
        ensure_reseller_privileges(user, can_create_packages=can_create_packages)
