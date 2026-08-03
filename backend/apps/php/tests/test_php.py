"""Tests module PHP multi-version."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, UserFactory
from apps.core.exceptions import VZoneAPIException
from apps.php.models import PhpSelector, PhpVersion
from apps.php.services import create_selector, ensure_default_versions


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def php_root(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_PHP_CONFIG_DIR = str(tmp_path / "php")
    settings.VZONE_PHP_PROVISION_MODE = "mock"
    return settings.VZONE_HOME_ROOT


@pytest.mark.integration
@pytest.mark.django_db
def test_list_versions_and_create_selector(api: APIClient, php_root):
    user = UserFactory(username="phpuser", password="TestPassword123!")
    api.force_authenticate(user=user)

    versions = api.get(reverse("php-version-list"))
    assert versions.status_code == 200
    data = versions.json()["data"]
    assert len(data) >= 3
    version_id = next(v["id"] for v in data if v["version"] == "8.3")

    created = api.post(
        reverse("php-selector-list"),
        {
            "php_version_id": version_id,
            "relative_path": "public_html",
            "domain_name": "example.test",
            "handler": "fpm",
            "ini_settings": {"memory_limit": "512M"},
        },
        format="json",
    )
    assert created.status_code == 201
    sel = created.json()["data"]
    assert sel["php_version_string"] == "8.3"
    assert sel["relative_path"] == "public_html"
    assert sel["ini_settings"]["memory_limit"] == "512M"

    home = Path(php_root) / "phpuser" / "public_html"
    assert (home / ".user.ini").exists()
    assert "memory_limit = 512M" in (home / ".user.ini").read_text(encoding="utf-8")
    assert (home / ".htaccess").exists()

    overview = api.get(reverse("php-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["selectors"] == 1
    assert overview.json()["data"]["default_version"] == "8.3"


@pytest.mark.integration
@pytest.mark.django_db
def test_update_and_delete_selector(api: APIClient, php_root):
    user = UserFactory(username="php2")
    ensure_default_versions()
    v82 = PhpVersion.objects.get(version="8.2")
    v81 = PhpVersion.objects.get(version="8.1")
    selector = create_selector(owner=user, php_version_id=v82.pk, relative_path="public_html")
    api.force_authenticate(user=user)

    patched = api.patch(
        reverse("php-selector-detail", kwargs={"pk": selector.pk}),
        {"php_version_id": v81.pk, "ini_settings": {"display_errors": "On"}},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["php_version_string"] == "8.1"

    deleted = api.delete(reverse("php-selector-detail", kwargs={"pk": selector.pk}))
    assert deleted.status_code == 204
    assert PhpSelector.objects.count() == 0


@pytest.mark.integration
@pytest.mark.django_db
def test_admin_set_default(api: APIClient, php_root):
    admin = AdminFactory(password="TestPassword123!")
    ensure_default_versions()
    v84 = PhpVersion.objects.get(version="8.4")
    api.force_authenticate(user=admin)
    resp = api.post(reverse("php-version-default", kwargs={"pk": v84.pk}))
    assert resp.status_code == 200
    assert resp.json()["data"]["is_default"] is True
    assert PhpVersion.objects.get(version="8.3").is_default is False


@pytest.mark.unit
@pytest.mark.django_db
def test_duplicate_path_rejected(php_root):
    user = UserFactory(username="php3")
    ensure_default_versions()
    v = PhpVersion.objects.get(is_default=True)
    create_selector(owner=user, php_version_id=v.pk, relative_path="public_html")
    with pytest.raises(VZoneAPIException):
        create_selector(owner=user, php_version_id=v.pk, relative_path="public_html")
