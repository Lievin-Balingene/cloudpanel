"""Tests V-zone Pulse Resource Governor."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, UserFactory
from apps.packages.models import HostingPackage
from apps.packages.pulse import apply_pulse_for_user, status_for_user
from apps.packages.services import apply_package_to_user


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.mark.integration
@pytest.mark.django_db
def test_pulse_apply_and_status(api: APIClient, tmp_path, settings):
    settings.VZONE_PULSE_MODE = "mock"
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_LINUX_USER_PROVISION = "mock"

    admin = AdminFactory()
    client = UserFactory(username="pulseuser")
    pkg = HostingPackage.objects.create(
        name="Pulse Plan",
        package_type="client",
        cpu_millicores=1500,
        ram_mb=2048,
        max_processes=80,
        inode_limit=100000,
    )
    apply_package_to_user(client, pkg, assigned_by=admin)
    result = apply_pulse_for_user(client)
    assert result.get("ok") is True or result.get("active") is True or result.get("mock") is True

    status = status_for_user(client)
    assert status["engine"] == "pulse"
    assert status["cpu"]["millicores_limit"] == 1500
    assert status["memory"]["limit_mb"] == 2048

    api.force_authenticate(user=admin)
    overview = api.get(reverse("pulse-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["brand"] == "V-zone Pulse"

    api.force_authenticate(user=client)
    mine = api.get(reverse("pulse-mine"))
    assert mine.status_code == 200
    assert mine.json()["data"]["username"] == "pulseuser"
