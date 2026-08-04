"""Tests module WordPress (mode mock)."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.domains.models import Domain
from apps.domains.services import create_domain
from apps.wordpress.models import WordPressSite


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def wp_env(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_WORDPRESS_PROVISION_MODE = "mock"
    settings.VZONE_DB_PROVISION_MODE = "mock"
    settings.VZONE_PHP_PROVISION_MODE = "mock"
    settings.VZONE_PHP_CONFIG_DIR = str(tmp_path / "php")
    settings.VZONE_DB_MAPS_DIR = str(tmp_path / "dbmaps")
    settings.VZONE_WEB_STACK = "mock"
    return settings.VZONE_HOME_ROOT


@pytest.mark.integration
@pytest.mark.django_db
def test_install_and_delete_wordpress(api: APIClient, wp_env):
    user = UserFactory(username="wpuser", password="TestPassword123!", email="wp@example.com")
    api.force_authenticate(user=user)

    domain = create_domain(
        owner=user,
        name="wp.example.test",
        domain_type=Domain.DomainType.PRIMARY,
        create_dns_zone=False,
    )
    assert Path(domain.document_root).exists()

    created = api.post(
        reverse("wordpress-site-list"),
        {
            "domain_id": domain.pk,
            "title": "Site Test",
            "admin_user": "wpadmin",
            "admin_email": "admin@example.com",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    data = created.json()["data"]
    assert data["status"] == "active"
    assert data["domain_name"] == "wp.example.test"
    assert data["admin_password"]
    assert (Path(domain.document_root) / "wp-config.php").exists()
    assert (Path(domain.document_root) / "index.php").exists()
    pk = data["id"]

    overview = api.get(reverse("wordpress-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["sites"] == 1

    listed = api.get(reverse("wordpress-site-list"))
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1

    deleted = api.delete(reverse("wordpress-site-detail", kwargs={"pk": pk}))
    assert deleted.status_code == 204
    assert not WordPressSite.objects.filter(pk=pk).exists()
    assert not (Path(domain.document_root) / "wp-config.php").exists()


@pytest.mark.integration
@pytest.mark.django_db
def test_cannot_install_twice(api: APIClient, wp_env):
    user = UserFactory(username="wp2", email="wp2@example.com")
    api.force_authenticate(user=user)
    domain = create_domain(owner=user, name="twice.example.test", create_dns_zone=False)
    first = api.post(
        reverse("wordpress-site-list"),
        {"domain_id": domain.pk, "title": "One"},
        format="json",
    )
    assert first.status_code == 201
    second = api.post(
        reverse("wordpress-site-list"),
        {"domain_id": domain.pk, "title": "Two"},
        format="json",
    )
    assert second.status_code == 400
