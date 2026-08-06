"""Tests d'authentification et de gestion des utilisateurs."""
from __future__ import annotations

from pathlib import Path

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
def test_login_with_username(api: APIClient):
    user = UserFactory(email="client@vzone.test", username="client1", password="TestPassword123!")
    response = api.post(
        reverse("auth-login"),
        {"email": "client1", "password": "TestPassword123!"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["data"]["user"]["username"] == user.username


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
def test_reseller_creates_client_only(api: APIClient, tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_NGINX_DOMAINS_DIR = str(tmp_path / "nginx")
    settings.VZONE_PUBLIC_IP = "203.0.113.10"
    Path(settings.VZONE_NGINX_DOMAINS_DIR).mkdir(parents=True, exist_ok=True)

    reseller = ResellerFactory(password="TestPassword123!")
    api.force_authenticate(user=reseller)

    # Sans domaine → erreur
    missing = api.post(
        reverse("user-list"),
        {
            "email": "nodomain@vzone.test",
            "username": "nodomain",
            "password": "TestPassword123!",
            "role": "client",
        },
        format="json",
    )
    assert missing.status_code == 400

    response = api.post(
        reverse("user-list"),
        {
            "email": "newclient@vzone.test",
            "username": "newclient",
            "password": "TestPassword123!",
            "role": "client",
            "domain": "newclient.example.com",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    data = response.json()["data"]
    assert data.get("primary_domain") == "newclient.example.com"

    created = User.objects.get(username="newclient")
    assert created.parent_id == reseller.pk
    assert created.system_username == "newclient"
    home = settings.VZONE_HOME_ROOT / "newclient"
    assert Path(created.home_directory).resolve() == home.resolve()
    assert (home / "public_html").is_dir()
    assert (home / "mail").is_dir()
    assert (home / "etc").is_dir()
    assert (home / "ssl").is_dir()
    assert (home / ".trash").is_dir()
    # Pas d'index.html par défaut (opt-in create_welcome_index)
    assert not (home / "public_html" / "index.html").exists()

    with_index = api.post(
        reverse("user-list"),
        {
            "email": "withindex@vzone.test",
            "username": "withidx",
            "password": "TestPassword123!",
            "role": "client",
            "domain": "withindex.example.com",
            "create_welcome_index": True,
        },
        format="json",
    )
    assert with_index.status_code == 201, with_index.content
    idx_home = settings.VZONE_HOME_ROOT / "withidx"
    assert (idx_home / "public_html" / "index.html").is_file()
    assert "withindex.example.com" in (idx_home / "public_html" / "index.html").read_text(
        encoding="utf-8"
    )

    from apps.domains.models import Domain
    from apps.dns.models import DnsRecord, DnsZone

    primary = Domain.objects.get(owner=created, domain_type=Domain.DomainType.PRIMARY)
    assert primary.name == "newclient.example.com"
    assert primary.document_root.endswith("public_html")
    zone = DnsZone.objects.get(name="newclient.example.com")
    assert DnsRecord.objects.filter(zone=zone, record_type="A", name="@").exists()
    vhost = Path(settings.VZONE_NGINX_DOMAINS_DIR) / "newclient.example.com.conf"
    assert vhost.exists()
    conf = vhost.read_text(encoding="utf-8")
    assert "server_name" in conf
    assert "newclient.example.com" in conf
    assert "public_html" in conf.replace("\\", "/")

    forbidden = api.post(
        reverse("user-list"),
        {
            "email": "other@vzone.test",
            "username": "other",
            "password": "TestPassword123!",
            "role": "reseller",
            "domain": "other.example.com",
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

    resume = api.post(
        reverse("user-suspend", kwargs={"pk": client_user.pk}),
        {"suspended": False},
        format="json",
    )
    assert resume.status_code == 200
    client_user.refresh_from_db()
    assert client_user.is_suspended is False
    assert client_user.is_active is True


@pytest.mark.integration
@pytest.mark.django_db
def test_update_and_delete_user(api: APIClient, tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    admin = AdminFactory(password="TestPassword123!")
    api.force_authenticate(user=admin)
    created = api.post(
        reverse("user-list"),
        {
            "email": "editme@vzone.test",
            "username": "editme",
            "password": "TestPassword123!",
            "role": "client",
            "domain": "editme.example.com",
        },
        format="json",
    )
    assert created.status_code == 201
    uid = created.json()["data"]["id"]
    home = settings.VZONE_HOME_ROOT / "editme"
    assert home.exists()

    patched = api.patch(
        reverse("user-detail", kwargs={"pk": uid}),
        {"email": "edited@vzone.test", "first_name": "Ed"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["email"] == "edited@vzone.test"

    deleted = api.delete(reverse("user-detail", kwargs={"pk": uid}))
    assert deleted.status_code == 204
    assert not User.objects.filter(pk=uid).exists()
    assert not home.exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_quota_defaults():
    user = UserFactory()
    assert hasattr(user, "quota")
    assert user.quota.disk_mb == 10240
    assert user.quota.domains == 5
