"""Tests module FTP."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.ftp.models import FtpAccount, FtpLog
from apps.ftp.services import authenticate_ftp, create_ftp_account, suspend_ftp_account


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def home_root(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_FTP_VIRTUAL_USERS_FILE = str(tmp_path / "ftp" / "virtual_users")
    settings.VZONE_FTP_AUTH_SECRET = "test-ftp-secret"
    return settings.VZONE_HOME_ROOT


@pytest.mark.integration
@pytest.mark.django_db
def test_create_list_suspend_ftp_account(api: APIClient, home_root):
    user = UserFactory(username="site1", password="TestPassword123!")
    api.force_authenticate(user=user)

    create = api.post(
        reverse("ftp-account-list"),
        {
            "username": "web",
            "password": "FtpPass123!",
            "relative_directory": "public_html",
        },
        format="json",
    )
    assert create.status_code == 201
    data = create.json()["data"]
    assert data["username"] == "site1_web"
    assert data["status"] == "active"
    assert Path(data["directory"]).exists()

    listing = api.get(reverse("ftp-account-list"))
    assert listing.status_code == 200
    assert len(listing.json()["data"]) == 1

    pk = data["id"]
    suspend = api.post(reverse("ftp-account-suspend", kwargs={"pk": pk}), {"suspended": True}, format="json")
    assert suspend.status_code == 200
    assert suspend.json()["data"]["status"] == "suspended"

    stats = api.get(reverse("ftp-stats"))
    assert stats.status_code == 200
    assert stats.json()["data"]["accounts_suspended"] == 1


@pytest.mark.integration
@pytest.mark.django_db
def test_ftp_auth_and_logs(api: APIClient, home_root):
    user = UserFactory(username="site2")
    account = create_ftp_account(
        owner=user,
        username="docs",
        password="FtpPass123!",
        relative_directory="public_html",
    )

    ok = api.post(
        reverse("ftp-auth"),
        {"username": account.username, "password": "FtpPass123!", "ip_address": "203.0.113.50"},
        format="json",
        HTTP_X_VZONE_FTP_SECRET="test-ftp-secret",
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["directory"] == account.directory

    bad = api.post(
        reverse("ftp-auth"),
        {"username": account.username, "password": "wrong-pass", "ip_address": "203.0.113.50"},
        format="json",
        HTTP_X_VZONE_FTP_SECRET="test-ftp-secret",
    )
    assert bad.status_code == 401

    nosecret = api.post(
        reverse("ftp-auth"),
        {"username": account.username, "password": "FtpPass123!"},
        format="json",
    )
    assert nosecret.status_code == 403

    api.force_authenticate(user=user)
    logs = api.get(reverse("ftp-log-list"))
    assert logs.status_code == 200
    events = {item["event_type"] for item in logs.json()["data"]}
    assert "login" in events
    assert "login_failed" in events


@pytest.mark.integration
@pytest.mark.django_db
def test_ftp_quota(api: APIClient, home_root):
    user = UserFactory(username="site3")
    user.quota.ftp_accounts = 1
    user.quota.save()
    create_ftp_account(owner=user, username="one", password="FtpPass123!")
    api.force_authenticate(user=user)
    second = api.post(
        reverse("ftp-account-list"),
        {"username": "two", "password": "FtpPass123!"},
        format="json",
    )
    assert second.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_authenticate_helper(home_root):
    user = UserFactory(username="site4")
    account = create_ftp_account(owner=user, username="mail", password="FtpPass123!")
    assert authenticate_ftp(account.username, "FtpPass123!") is not None
    suspend_ftp_account(account, True)
    assert authenticate_ftp(account.username, "FtpPass123!") is None
    assert FtpLog.objects.filter(event_type="login_failed").exists()
