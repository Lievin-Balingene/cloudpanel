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
def test_client_overview_disk_is_home_only(api: APIClient, tmp_path, settings):
    """Le Disk Usage client mesure uniquement son home, pas le disque serveur."""
    from apps.dashboard.services import overview_for
    from apps.domains.models import Domain
    from apps.packages.services import apply_package_to_user, seed_default_packages

    settings.VZONE_HOME_ROOT = str(tmp_path)
    client_user = UserFactory(password="TestPassword123!", role="client", username="diskuser")
    seed_default_packages()
    pkg = HostingPackage.objects.filter(package_type="client", is_default=True).first()
    assert pkg is not None
    pkg.disk_mb = 100
    pkg.unlimited_disk = False
    pkg.save(update_fields=["disk_mb", "unlimited_disk"])
    apply_package_to_user(client_user, pkg)

    home = tmp_path / "diskuser"
    home.mkdir(parents=True)
    (home / "public_html").mkdir()
    payload = b"x" * (2 * 1024 * 1024)  # 2 Mo
    (home / "public_html" / "big.bin").write_bytes(payload)

    Domain.objects.create(
        name="diskuser.test",
        owner=client_user,
        domain_type=Domain.DomainType.PRIMARY,
        document_root=str(home / "public_html"),
    )

    body = overview_for(client_user)
    assert body["account"]["home_directory"].endswith("diskuser")
    assert body["account"]["primary_domain"] == "diskuser.test"
    assert body["metrics"] is None
    assert body["disk"]["used"] >= len(payload)
    assert body["disk"]["quota_mb"] == 100
    assert body["disk"]["total"] == 100 * 1024 * 1024
    assert body["disk"]["unlimited"] is False
    assert body["disk"]["used_mb"] >= 2
    assert body["disk"]["home_directory"].endswith("diskuser")
    assert "public_html" in body["disk"]["breakdown_mb"]
    assert body["usage"]["domains"] == 1
    # Ne doit pas refléter le disque système (souvent des Go)
    assert body["disk"]["used"] < 50 * 1024 * 1024


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
