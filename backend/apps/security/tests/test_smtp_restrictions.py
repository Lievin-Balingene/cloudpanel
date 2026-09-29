"""Tests SMTP Restrictions."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, UserFactory
from apps.security.smtp_restrictions import get_status, set_enabled


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.mark.integration
@pytest.mark.django_db
def test_smtp_restrictions_toggle(api: APIClient, tmp_path, settings):
    settings.VZONE_SMTP_RESTRICT_MODE = "mock"
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)

    admin = AdminFactory(username="rootadmin", password="TestPassword123!")
    api.force_authenticate(user=admin)

    status = api.get(reverse("security-smtp-restrictions"))
    assert status.status_code == 200
    assert status.json()["data"]["enabled"] is False
    assert "spammers" in status.json()["data"]["description"].lower() or "mail server" in status.json()["data"]["description"].lower()

    enable = api.post(reverse("security-smtp-restrictions"), {"enabled": True}, format="json")
    assert enable.status_code == 200
    assert enable.json()["data"]["enabled"] is True

    again = get_status()
    assert again["enabled"] is True

    disable = api.post(reverse("security-smtp-restrictions"), {"action": "disable"}, format="json")
    assert disable.status_code == 200
    assert disable.json()["data"]["enabled"] is False


@pytest.mark.unit
@pytest.mark.django_db
def test_smtp_restrictions_set_enabled_syncs_tweak(tmp_path, settings):
    settings.VZONE_SMTP_RESTRICT_MODE = "mock"
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)

    set_enabled(True)
    from apps.server_setup.models import ServerSetup
    from apps.server_setup.tweak_settings import merge_tweaks

    setup = ServerSetup.get_solo()
    values = merge_tweaks(setup.tweak_settings)
    assert values.get("smtp_restrictions") is True

    set_enabled(False)
    setup.refresh_from_db()
    values = merge_tweaks(setup.tweak_settings)
    assert values.get("smtp_restrictions") is False


@pytest.mark.integration
@pytest.mark.django_db
def test_smtp_restrictions_admin_only(api: APIClient, tmp_path, settings):
    settings.VZONE_SMTP_RESTRICT_MODE = "mock"
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)

    client = UserFactory(username="smtpcli", role="client", password="TestPassword123!")
    api.force_authenticate(user=client)
    resp = api.get(reverse("security-smtp-restrictions"))
    assert resp.status_code == 403
