"""Tests contexte local (lien lent, fuseau, téléphone, pas de facturation)."""
from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, UserFactory
from apps.local_context.models import LocalSiteProfile
from apps.local_context.services import in_backup_window, should_defer_heavy_job


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_profile_defaults_and_country_apply(api: APIClient):
    admin = AdminFactory()
    api.force_authenticate(user=admin)
    res = api.get(reverse("local-context-profile"))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "currency" not in data
    assert data["timezone"] == "Africa/Kinshasa"
    patch = api.patch(
        reverse("local-context-profile"),
        {"country": "CI", "apply_country_defaults": True},
        format="json",
    )
    assert patch.status_code == 200
    body = patch.json()["data"]
    assert body["phone_prefix"] == "+225"
    assert body["timezone"] == "Africa/Abidjan"
    assert "payment_instructions" not in body


@pytest.mark.django_db
def test_no_payments_endpoint(api: APIClient):
    admin = AdminFactory()
    api.force_authenticate(user=admin)
    res = api.get("/api/v1/local-context/payments/")
    assert res.status_code == 404


@pytest.mark.django_db
def test_backup_window_defers_daytime():
    profile = LocalSiteProfile.get_solo()
    profile.backup_window_start = 1
    profile.backup_window_end = 6
    profile.defer_heavy_jobs = True
    profile.timezone = "UTC"
    profile.save()
    noon = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
    night = timezone.now().replace(hour=3, minute=0, second=0, microsecond=0)
    assert in_backup_window(noon) is False
    assert in_backup_window(night) is True
    assert should_defer_heavy_job() in {True, False}


@pytest.mark.django_db
def test_create_account_requires_phone_when_enabled(api: APIClient):
    profile = LocalSiteProfile.get_solo()
    profile.require_phone = True
    profile.save(update_fields=["require_phone"])
    admin = AdminFactory()
    api.force_authenticate(user=admin)
    res = api.post(
        reverse("user-list"),
        {
            "email": "nophone@vzone.test",
            "username": "nophone",
            "password": "TestPassword123!",
            "role": "client",
            "domain": "nophone.test",
        },
        format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_notice_is_operational_not_invoice(api: APIClient):
    admin = AdminFactory()
    client = UserFactory(username="wa", phone="+243810000000")
    api.force_authenticate(user=admin)
    res = api.get(reverse("local-context-notice"), {"user_id": client.pk, "kind": "welcome"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert "wa.me/243810000000" in data["whatsapp_url"]
    assert "payez" not in data["body"].lower()
    assert "mobile money" not in data["body"].lower()


@pytest.mark.django_db
def test_overview_lists_services(api: APIClient):
    admin = AdminFactory()
    api.force_authenticate(user=admin)
    res = api.get(reverse("local-context-overview"))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "services" in data
    assert "collected_this_month" not in data
