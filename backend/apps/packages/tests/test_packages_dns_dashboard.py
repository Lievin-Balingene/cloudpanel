"""Tests packages, DNS et dashboard."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, UserFactory
from apps.dns.services import create_zone_with_defaults
from apps.packages.models import HostingPackage
from apps.packages.services import apply_package_to_user, seed_default_packages


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.mark.integration
@pytest.mark.django_db
def test_seed_and_assign_package(api: APIClient):
    admin = AdminFactory(password="TestPassword123!")
    client_user = UserFactory(password="TestPassword123!")
    api.force_authenticate(user=admin)

    seed = api.post(reverse("package-seed"))
    assert seed.status_code == 200
    assert HostingPackage.objects.filter(package_type="client").exists()

    pkg = HostingPackage.objects.filter(package_type="client", is_default=True).first()
    assert pkg is not None
    assign = api.post(
        reverse("package-assign"),
        {"user_id": client_user.pk, "package_id": pkg.pk},
        format="json",
    )
    assert assign.status_code == 200
    client_user.refresh_from_db()
    assert client_user.quota.disk_mb == pkg.disk_mb


@pytest.mark.integration
@pytest.mark.django_db
def test_dns_zone_and_records(api: APIClient):
    admin = AdminFactory(password="TestPassword123!")
    api.force_authenticate(user=admin)
    create = api.post(
        reverse("dns-zone-list"),
        {"name": "exemple.com"},
        format="json",
    )
    assert create.status_code == 201
    zone_id = create.json()["data"]["id"]
    assert create.json()["data"]["record_count"] >= 2

    rec = api.post(
        reverse("dns-record-list", kwargs={"zone_id": zone_id}),
        {"record_type": "A", "name": "www", "content": "1.2.3.4", "ttl": 300},
        format="json",
    )
    assert rec.status_code == 201

    detail = api.get(reverse("dns-zone-detail", kwargs={"pk": zone_id}))
    assert detail.status_code == 200
    assert detail.json()["data"]["soa_serial"] >= 1


@pytest.mark.integration
@pytest.mark.django_db
def test_dashboard_overview_and_capture(api: APIClient):
    admin = AdminFactory(password="TestPassword123!")
    api.force_authenticate(user=admin)
    overview = api.get(reverse("dashboard-overview"))
    assert overview.status_code == 200
    body = overview.json()["data"]
    assert "users_total" in body
    assert "services" in body

    capture = api.post(reverse("dashboard-capture"))
    assert capture.status_code == 200

    history = api.get(reverse("dashboard-history"))
    assert history.status_code == 200
    assert len(history.json()["data"]) >= 1


@pytest.mark.integration
@pytest.mark.django_db
def test_update_and_delete_package(api: APIClient):
    admin = AdminFactory(password="TestPassword123!")
    api.force_authenticate(user=admin)
    seed_default_packages()
    pkg = HostingPackage.objects.filter(package_type="client").first()
    assert pkg is not None

    updated = api.patch(
        reverse("package-detail", kwargs={"pk": pkg.pk}),
        {"emails": 99, "name": pkg.name},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["emails"] == 99

    lonely = api.post(
        reverse("package-list"),
        {
            "name": "TempPlan",
            "package_type": "client",
            "disk_mb": 1000,
            "domains": 1,
            "emails": 1,
            "databases": 1,
        },
        format="json",
    )
    assert lonely.status_code == 201
    lid = lonely.json()["data"]["id"]
    deleted = api.delete(reverse("package-detail", kwargs={"pk": lid}))
    assert deleted.status_code == 204
    assert not HostingPackage.objects.filter(pk=lid).exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_apply_package_syncs_quota():
    seed_default_packages()
    user = UserFactory()
    pkg = HostingPackage.objects.get(name="Business")
    apply_package_to_user(user, pkg)
    user.refresh_from_db()
    assert user.quota.domains == pkg.domains
    assert user.package_assignment.package_id == pkg.pk


@pytest.mark.unit
@pytest.mark.django_db
def test_create_zone_defaults():
    user = UserFactory()
    zone = create_zone_with_defaults(name="demo.test", owner=user)
    assert zone.records.filter(record_type="NS").count() == 2
