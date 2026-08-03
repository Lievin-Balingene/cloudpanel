"""Services d'assignation et synchronisation des quotas."""
from __future__ import annotations

from django.db import transaction

from apps.accounts.models import ResourceQuota, User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.packages.models import HostingPackage, PackageAssignment


def get_default_package(package_type: str) -> HostingPackage | None:
    return (
        HostingPackage.objects.filter(
            package_type=package_type,
            is_active=True,
            is_default=True,
            owner__isnull=True,
        ).first()
        or HostingPackage.objects.filter(
            package_type=package_type,
            is_active=True,
            owner__isnull=True,
        )
        .order_by("sort_order", "name")
        .first()
    )


@transaction.atomic
def apply_package_to_user(
    user: User,
    package: HostingPackage,
    *,
    assigned_by: User | None = None,
    notes: str = "",
) -> PackageAssignment:
    """Assigne un package et synchronise ResourceQuota."""
    if not package.is_active:
        raise VZoneAPIException(
            detail="Ce package est désactivé.",
            code="package_inactive",
            status_code=400,
        )

    if user.role == User.Role.CLIENT and package.package_type != HostingPackage.PackageType.CLIENT:
        raise VZoneAPIException(
            detail="Un compte client nécessite un package de type client.",
            code="package_type_mismatch",
            status_code=400,
        )
    if user.role == User.Role.RESELLER and package.package_type != HostingPackage.PackageType.RESELLER:
        raise VZoneAPIException(
            detail="Un revendeur nécessite un package de type revendeur.",
            code="package_type_mismatch",
            status_code=400,
        )

    if assigned_by and assigned_by.role == User.Role.RESELLER:
        _assert_reseller_can_assign(assigned_by, package, user)

    quota, _ = ResourceQuota.objects.get_or_create(user=user)
    for key, value in package.quota_payload().items():
        setattr(quota, key, value)
    quota.save()

    assignment, _ = PackageAssignment.objects.update_or_create(
        user=user,
        defaults={
            "package": package,
            "assigned_by": assigned_by,
            "notes": notes,
        },
    )
    return assignment


def _assert_reseller_can_assign(
    reseller: User,
    package: HostingPackage,
    target: User,
) -> None:
    if target.parent_id != reseller.pk and target.pk != reseller.pk:
        raise VZoneAPIException(
            detail="Ce compte n'appartient pas à ce revendeur.",
            code="forbidden",
            status_code=403,
        )
    if package.owner_id not in (None, reseller.pk):
        raise VZoneAPIException(
            detail="Package non autorisé pour ce revendeur.",
            code="package_forbidden",
            status_code=403,
        )
    reseller_assignment = PackageAssignment.objects.filter(user=reseller).select_related("package").first()
    if reseller_assignment and reseller_assignment.package.max_accounts:
        current = User.objects.filter(parent=reseller, role=User.Role.CLIENT).count()
        if target.pk is None or not User.objects.filter(pk=target.pk, parent=reseller).exists():
            if current >= reseller_assignment.package.max_accounts:
                raise QuotaExceeded(
                    detail="Nombre maximal de comptes atteint pour ce revendeur.",
                    extra={"max_accounts": reseller_assignment.package.max_accounts},
                )


def seed_default_packages() -> list[HostingPackage]:
    """Crée les packages système de base s'ils n'existent pas."""
    defaults = [
        {
            "name": "Starter",
            "package_type": HostingPackage.PackageType.CLIENT,
            "is_default": True,
            "disk_mb": 5120,
            "bandwidth_mb": 51200,
            "domains": 1,
            "emails": 5,
            "databases": 2,
            "sort_order": 10,
        },
        {
            "name": "Business",
            "package_type": HostingPackage.PackageType.CLIENT,
            "disk_mb": 20480,
            "bandwidth_mb": 204800,
            "domains": 5,
            "emails": 25,
            "databases": 10,
            "python_apps": 3,
            "node_apps": 3,
            "sort_order": 20,
        },
        {
            "name": "Reseller Basic",
            "package_type": HostingPackage.PackageType.RESELLER,
            "is_default": True,
            "disk_mb": 102400,
            "bandwidth_mb": 1024000,
            "domains": 50,
            "emails": 200,
            "databases": 50,
            "max_accounts": 25,
            "can_create_packages": True,
            "unlimited_disk": False,
            "sort_order": 10,
        },
    ]
    created: list[HostingPackage] = []
    for item in defaults:
        obj, was_created = HostingPackage.objects.get_or_create(
            name=item["name"],
            defaults=item,
        )
        if was_created:
            created.append(obj)
    return created
