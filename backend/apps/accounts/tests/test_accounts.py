"""Tests d'authentification et de gestion des utilisateurs."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, ResellerFactory, UserFactory
from apps.accounts.models import User


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.mark.integration
@pytest.mark.django_db
def test_login_success(api: APIClient):
    user = UserFactory(email="client@vzone.test", username="client1", password="TestPassword123!")
    response = api.post(
        reverse("auth-login"),
        {"email": "client@vzone.test", "password": "TestPassword123!"},
        format="json",
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "access" in data["tokens"]
    assert data["user"]["username"] == user.username


@pytest.mark.integration
@pytest.mark.django_db
def test_login_invalid(api: APIClient):
    UserFactory(email="client@vzone.test", username="client1", password="TestPassword123!")
    response = api.post(
        reverse("auth-login"),
        {"email": "client@vzone.test", "password": "wrong-password"},
        format="json",
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.integration
@pytest.mark.django_db
def test_me_requires_auth(api: APIClient):
    response = api.get(reverse("auth-me"))
    assert response.status_code in {401, 403}


@pytest.mark.integration
@pytest.mark.django_db
def test_me_authenticated(api: APIClient):
    user = AdminFactory(password="TestPassword123!")
    api.force_authenticate(user=user)
    response = api.get(reverse("auth-me"))
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "administrator"


@pytest.mark.integration
@pytest.mark.django_db
def test_reseller_creates_client_only(api: APIClient):
    reseller = ResellerFactory(password="TestPassword123!")
    api.force_authenticate(user=reseller)
    response = api.post(
        reverse("user-list"),
        {
            "email": "newclient@vzone.test",
            "username": "newclient",
            "password": "TestPassword123!",
            "role": "client",
        },
        format="json",
    )
    assert response.status_code == 201
    created = User.objects.get(username="newclient")
    assert created.parent_id == reseller.pk

    forbidden = api.post(
        reverse("user-list"),
        {
            "email": "other@vzone.test",
            "username": "other",
            "password": "TestPassword123!",
            "role": "reseller",
        },
        format="json",
    )
    assert forbidden.status_code == 400


@pytest.mark.integration
@pytest.mark.django_db
def test_admin_lists_modules(api: APIClient):
    admin = AdminFactory(password="TestPassword123!")
    api.force_authenticate(user=admin)
    response = api.get(reverse("module-list"))
    assert response.status_code == 200
    names = {m["name"] for m in response.json()["data"]}
    assert "core" in names
    assert "accounts" in names
    assert "packages" in names
    assert "dns" in names
    assert "dashboard" in names
    assert "domains" in names
    assert "files" in names
    assert "ftp" in names
    assert "email" in names
    assert "databases" in names
    assert "python_apps" in names
    assert "node_apps" in names
    assert "php" in names
    assert "git_deploy" in names
    assert "docker_mgmt" in names
    assert "backups" in names
    assert "monitoring" in names
    assert "firewall" in names
    assert "security" in names


@pytest.mark.integration
@pytest.mark.django_db
def test_change_password(api: APIClient):
    user = UserFactory(password="TestPassword123!")
    api.force_authenticate(user=user)
    response = api.post(
        reverse("auth-password"),
        {
            "current_password": "TestPassword123!",
            "new_password": "NewSecurePass456!",
        },
        format="json",
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password("NewSecurePass456!")


@pytest.mark.integration
@pytest.mark.django_db
def test_suspend_user(api: APIClient):
    admin = AdminFactory(password="TestPassword123!")
    client_user = UserFactory(password="TestPassword123!")
    api.force_authenticate(user=admin)
    response = api.post(reverse("user-suspend", kwargs={"pk": client_user.pk}))
    assert response.status_code == 200
    client_user.refresh_from_db()
    assert client_user.is_suspended is True
    assert client_user.is_active is False


@pytest.mark.unit
@pytest.mark.django_db
def test_quota_defaults():
    user = UserFactory()
    assert hasattr(user, "quota")
    assert user.quota.disk_mb == 10240
    assert user.quota.domains == 5
