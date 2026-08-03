"""Tests module Firewall / Fail2Ban."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.accounts.models import User
from apps.firewall.models import Fail2BanBan, FirewallRule
from apps.firewall.services import apply_rule, ban_ip, create_rule, unban_ip


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def fw_root(tmp_path, settings):
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_FIREWALL_CONFIG_DIR = str(tmp_path / "firewall")
    settings.VZONE_FIREWALL_PROVISION_MODE = "mock"
    return settings.VZONE_FIREWALL_CONFIG_DIR


@pytest.fixture
def admin_user(db):
    return UserFactory(
        username="fwadmin",
        password="TestPassword123!",
        role=User.Role.ADMINISTRATOR,
        is_staff=True,
    )


@pytest.mark.integration
@pytest.mark.django_db
def test_create_apply_rule(api: APIClient, admin_user, fw_root):
    api.force_authenticate(user=admin_user)
    created = api.post(
        reverse("firewall-rule-list"),
        {
            "name": "Allow HTTPS",
            "action": "allow",
            "protocol": "tcp",
            "port_start": 443,
            "apply_now": True,
        },
        format="json",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["name"] == "Allow HTTPS"
    assert data["is_applied"] is True
    pk = data["id"]

    overview = api.get(reverse("firewall-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["rules"] == 1
    assert overview.json()["data"]["provision_mode"] == "mock"

    deleted = api.delete(reverse("firewall-rule-detail", kwargs={"pk": pk}))
    assert deleted.status_code == 204
    assert FirewallRule.objects.count() == 0


@pytest.mark.integration
@pytest.mark.django_db
def test_fail2ban_ban_unban(api: APIClient, admin_user, fw_root):
    api.force_authenticate(user=admin_user)
    banned = api.post(
        reverse("firewall-f2b-ban"),
        {"ip_address": "203.0.113.10", "jail_name": "sshd", "reason": "bruteforce"},
        format="json",
    )
    assert banned.status_code == 201
    assert banned.json()["data"]["status"] == "active"

    bans = api.get(reverse("firewall-f2b-bans"))
    assert bans.status_code == 200
    assert len(bans.json()["data"]) == 1

    unbanned = api.post(
        reverse("firewall-f2b-unban"),
        {"ip_address": "203.0.113.10", "jail_name": "sshd"},
        format="json",
    )
    assert unbanned.status_code == 200
    assert unbanned.json()["data"]["unbanned"] == 1
    assert Fail2BanBan.objects.filter(status="active").count() == 0

    jails = api.get(reverse("firewall-f2b-jails") + "?sync=1")
    assert jails.status_code == 200
    assert len(jails.json()["data"]) >= 1


@pytest.mark.integration
@pytest.mark.django_db
def test_client_forbidden(api: APIClient, fw_root):
    client_user = UserFactory(username="fwclient", role=User.Role.CLIENT)
    api.force_authenticate(user=client_user)
    resp = api.get(reverse("firewall-overview"))
    assert resp.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_helpers(fw_root):
    rule = create_rule(name="SSH", protocol="tcp", port_start=22, apply_now=False)
    assert rule.is_applied is False
    rule = apply_rule(rule)
    assert rule.is_applied is True
    ban = ban_ip(ip_address="198.51.100.1", jail_name="sshd")
    assert ban.status == Fail2BanBan.Status.ACTIVE
    assert unban_ip(ip_address="198.51.100.1") == 1
