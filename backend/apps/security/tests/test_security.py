"""Tests module Sécurité avancée."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.accounts.models import User
from apps.security.models import AccountLockout, IpAccessRule
from apps.security.services import (
    assert_ip_allowed,
    create_ip_rule,
    get_policy,
    record_login_attempt,
    update_policy,
)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def admin_user(db):
    return UserFactory(
        username="secadmin",
        email="secadmin@example.com",
        password="TestPassword123!",
        role=User.Role.ADMINISTRATOR,
        is_staff=True,
    )


@pytest.mark.integration
@pytest.mark.django_db
def test_policy_and_overview(api: APIClient, admin_user):
    api.force_authenticate(user=admin_user)
    patched = api.patch(
        reverse("security-policy"),
        {
            "password_min_length": 12,
            "require_digit": True,
            "lockout_max_attempts": 3,
            "ip_mode": "blocklist",
        },
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["password_min_length"] == 12

    overview = api.get(reverse("security-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["policy"]["lockout_max_attempts"] == 3


@pytest.mark.integration
@pytest.mark.django_db
def test_ip_blocklist_blocks_login(api: APIClient, admin_user):
    update_policy(ip_mode="blocklist")
    create_ip_rule(cidr="127.0.0.1/32", list_type="block")
    resp = api.post(
        reverse("auth-login"),
        {"email": admin_user.email, "password": "TestPassword123!"},
        format="json",
        REMOTE_ADDR="127.0.0.1",
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ip_forbidden"


@pytest.mark.integration
@pytest.mark.django_db
def test_lockout_after_failures(api: APIClient, admin_user):
    update_policy(lockout_max_attempts=3, lockout_window_minutes=15, lockout_duration_minutes=30)
    for _ in range(3):
        api.post(
            reverse("auth-login"),
            {"email": admin_user.email, "password": "WrongPassword!!"},
            format="json",
            REMOTE_ADDR="203.0.113.50",
        )
    locked = api.post(
        reverse("auth-login"),
        {"email": admin_user.email, "password": "TestPassword123!"},
        format="json",
        REMOTE_ADDR="203.0.113.50",
    )
    assert locked.status_code == 403
    assert locked.json()["error"]["code"] == "locked_out"
    assert AccountLockout.objects.exists()


@pytest.mark.integration
@pytest.mark.django_db
def test_2fa_disable_and_me(api: APIClient, admin_user):
    import pyotp

    from apps.accounts.services import generate_totp_secret

    admin_user.two_factor_secret = generate_totp_secret()
    admin_user.two_factor_enabled = True
    admin_user.save()
    api.force_authenticate(user=admin_user)
    otp = pyotp.TOTP(admin_user.two_factor_secret).now()
    disabled = api.delete(reverse("auth-2fa"), data={"otp": otp}, format="json")
    assert disabled.status_code == 200
    admin_user.refresh_from_db()
    assert admin_user.two_factor_enabled is False

    me = api.get(reverse("security-me"))
    assert me.status_code == 200
    assert me.json()["data"]["two_factor_enabled"] is False


@pytest.mark.integration
@pytest.mark.django_db
def test_must_change_password_middleware(api: APIClient, admin_user):
    login = api.post(
        reverse("auth-login"),
        {"email": admin_user.email, "password": "TestPassword123!"},
        format="json",
    )
    assert login.status_code == 200
    token = login.json()["data"]["tokens"]["access"]
    admin_user.must_change_password = True
    admin_user.save(update_fields=["must_change_password"])
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    blocked = api.get(reverse("security-overview"))
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "must_change_password"

    allowed = api.get(reverse("security-me"))
    assert allowed.status_code == 200


@pytest.mark.unit
@pytest.mark.django_db
def test_helpers():
    policy = get_policy()
    assert policy.password_min_length >= 6
    update_policy(ip_mode="allowlist")
    create_ip_rule(cidr="10.0.0.0/8", list_type="allow")
    assert_ip_allowed("10.1.2.3")
    with pytest.raises(Exception):
        assert_ip_allowed("8.8.8.8")
    record_login_attempt(email="a@b.c", ip="1.2.3.4", success=False, message="fail")
    assert IpAccessRule.objects.count() == 1


@pytest.mark.unit
def test_build_runas_cmd_env_has_no_double_dash(tmp_path, settings, monkeypatch):
    """Busybox env traite ``--`` comme commande → code 127."""
    from apps.security import runas as runas_mod

    fake = tmp_path / "vzone-runas"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setattr(runas_mod, "RUNAS", fake)
    settings.VZONE_LINUX_USER_PROVISION = "live"
    settings.VZONE_ALLOW_UNJAILED_SUBPROCESS = False

    cmd = runas_mod.build_runas_cmd(
        "lievin",
        ["/home/lievin/virtualenv/vzone/3.12/bin/python", "-m", "gunicorn"],
        env={"PATH": "/usr/bin", "HOME": "/home/lievin"},
    )
    assert cmd[:5] == ["sudo", "-n", str(fake), "lievin", "--"]
    assert "env" in cmd
    # Après les KEY=VAL, la commande Python — jamais un "--" orphelin pour env
    env_idx = cmd.index("env")
    after_env = cmd[env_idx + 1 :]
    assert "--" not in after_env
    assert after_env[-3:] == [
        "/home/lievin/virtualenv/vzone/3.12/bin/python",
        "-m",
        "gunicorn",
    ]
