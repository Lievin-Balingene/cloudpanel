"""Tests WHM Login as (SSO handoff)."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, UserFactory
from apps.accounts.models import User


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_login_as_handoff_and_exchange(api: APIClient):
    admin = AdminFactory()
    client_user = UserFactory(username="cpaneluser", role=User.Role.CLIENT)
    api.force_authenticate(user=admin)
    created = api.post(reverse("user-login-as", kwargs={"pk": client_user.pk}))
    assert created.status_code == 200
    handoff = created.json()["data"]["handoff"]
    assert handoff

    api.logout()
    exchanged = api.post(reverse("auth-sso-exchange"), {"handoff": handoff}, format="json")
    assert exchanged.status_code == 200
    body = exchanged.json()["data"]
    assert "access" in body["tokens"]
    assert body["user"]["username"] == "cpaneluser"

    # one-shot
    again = api.post(reverse("auth-sso-exchange"), {"handoff": handoff}, format="json")
    assert again.status_code == 400


@pytest.mark.django_db
def test_login_as_cannot_target_admin(api: APIClient):
    admin = AdminFactory(username="a1")
    other = AdminFactory(username="a2", email="a2@example.com")
    api.force_authenticate(user=admin)
    res = api.post(reverse("user-login-as", kwargs={"pk": other.pk}))
    assert res.status_code == 403


@pytest.mark.django_db
def test_login_as_rejects_suspended(api: APIClient):
    admin = AdminFactory()
    client_user = UserFactory(
        username="suspended1",
        role=User.Role.CLIENT,
        is_suspended=True,
        is_active=False,
    )
    api.force_authenticate(user=admin)
    res = api.post(reverse("user-login-as", kwargs={"pk": client_user.pk}))
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "login_as_unavailable"
