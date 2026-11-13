"""Tests réinitialisation sécurisée du mot de passe (WHM)."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, UserFactory
from apps.accounts.models import User, UserSession
from apps.accounts.password_reset import generate_secure_password


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_generate_secure_password_meets_policy():
    pwd = generate_secure_password()
    assert len(pwd) >= 16
    assert any(c.isupper() for c in pwd)
    assert any(c.isdigit() for c in pwd)


@pytest.mark.django_db
def test_reset_password_requires_username_confirm(api: APIClient):
    admin = AdminFactory()
    client_user = UserFactory(username="acme", role=User.Role.CLIENT)
    api.force_authenticate(user=admin)
    bad = api.post(
        reverse("user-reset-password", kwargs={"pk": client_user.pk}),
        {"confirm_username": "wrong"},
        format="json",
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "password_reset_confirm_mismatch"


@pytest.mark.django_db
def test_reset_password_ok_forces_change_and_revokes_sessions(api: APIClient):
    admin = AdminFactory()
    client_user = UserFactory(username="acme", role=User.Role.CLIENT)
    from django.utils import timezone
    from datetime import timedelta

    UserSession.objects.create(
        user=client_user,
        jti="old-jti-1",
        user_agent="t",
        expires_at=timezone.now() + timedelta(days=30),
    )
    old_hash = client_user.password
    api.force_authenticate(user=admin)
    res = api.post(
        reverse("user-reset-password", kwargs={"pk": client_user.pk}),
        {"confirm_username": "acme"},
        format="json",
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["username"] == "acme"
    assert data["must_change_password"] is True
    assert data["shown_once"] is True
    assert len(data["temporary_password"]) >= 16

    client_user.refresh_from_db()
    assert client_user.must_change_password is True
    assert client_user.password != old_hash
    assert client_user.check_password(data["temporary_password"])
    assert not UserSession.objects.filter(user=client_user, is_revoked=False).exists()


@pytest.mark.django_db
def test_reset_password_cannot_target_admin(api: APIClient):
    admin = AdminFactory(username="root1")
    other = AdminFactory(username="root2", email="r2@example.com")
    api.force_authenticate(user=admin)
    res = api.post(
        reverse("user-reset-password", kwargs={"pk": other.pk}),
        {"confirm_username": "root2"},
        format="json",
    )
    assert res.status_code == 403


@pytest.mark.django_db
def test_reseller_can_reset_own_client(api: APIClient):
    reseller = UserFactory(username="rs1", role=User.Role.RESELLER)
    # Privileges edit-account
    from apps.accounts.models import ResellerPrivileges

    ResellerPrivileges.objects.update_or_create(
        user=reseller,
        defaults={"privileges": ["edit-account", "list-accts"]},
    )
    client_user = UserFactory(username="child1", role=User.Role.CLIENT, parent=reseller)
    api.force_authenticate(user=reseller)
    res = api.post(
        reverse("user-reset-password", kwargs={"pk": client_user.pk}),
        {"confirm_username": "child1"},
        format="json",
    )
    assert res.status_code == 200
    assert res.json()["data"]["must_change_password"] is True


@pytest.mark.django_db
def test_reseller_cannot_reset_foreign_client(api: APIClient):
    reseller = UserFactory(username="rs1", role=User.Role.RESELLER)
    from apps.accounts.models import ResellerPrivileges

    ResellerPrivileges.objects.update_or_create(
        user=reseller,
        defaults={"privileges": ["edit-account", "list-accts"]},
    )
    other = UserFactory(username="orphan", role=User.Role.CLIENT)
    api.force_authenticate(user=reseller)
    res = api.post(
        reverse("user-reset-password", kwargs={"pk": other.pk}),
        {"confirm_username": "orphan"},
        format="json",
    )
    assert res.status_code == 404
