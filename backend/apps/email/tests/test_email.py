"""Tests module e-mail."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.email.models import Mailbox, MailDomain, MailForwarder
from apps.email.services import create_mail_domain, create_mailbox, enable_dkim, write_mail_maps


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def mail_root(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_MAIL_MAPS_DIR = str(tmp_path / "mail")
    settings.VZONE_MAIL_STACK = "mock"
    settings.VZONE_MAIL_PUBLIC_IP = "203.0.113.10"
    settings.VZONE_WEBMAIL_URL = "/webmail/"
    return Path(settings.VZONE_MAIL_MAPS_DIR)


@pytest.mark.integration
@pytest.mark.django_db
def test_create_domain_mailbox_forwarder(api: APIClient, mail_root):
    user = UserFactory(username="mailuser", password="TestPassword123!")
    api.force_authenticate(user=user)

    domain = api.post(
        reverse("email-domain-list"),
        {"name": "example.test", "enable_dns": True, "max_quota_mb": 500},
        format="json",
    )
    assert domain.status_code == 201
    md_id = domain.json()["data"]["id"]
    assert domain.json()["data"]["spf_record"].startswith("v=spf1")
    assert "ip4:203.0.113.10" in domain.json()["data"]["spf_record"]
    assert "a:mail.example.test" in domain.json()["data"]["spf_record"]
    assert domain.json()["data"]["dkim_enabled"] is True
    assert domain.json()["data"]["dkim_public_key"]

    box = api.post(
        reverse("email-mailbox-list"),
        {
            "mail_domain_id": md_id,
            "local_part": "info",
            "password": "MailPass123!",
            "quota_mb": 100,
        },
        format="json",
    )
    assert box.status_code == 201
    assert box.json()["data"]["address"] == "info@example.test"
    maildir = Path(box.json()["data"]["maildir"])
    assert maildir.exists()
    assert maildir.parts[-2:] == ("example.test", "info")
    assert (maildir / "cur").is_dir()

    fwd = api.post(
        reverse("email-forwarder-list"),
        {
            "mail_domain_id": md_id,
            "local_part": "sales",
            "destinations": ["info@example.test"],
            "keep_copy": False,
        },
        format="json",
    )
    assert fwd.status_code == 201

    overview = api.get(reverse("email-overview"))
    assert overview.status_code == 200
    data = overview.json()["data"]
    assert data["domains"] == 1
    assert data["mailboxes"] == 1
    assert data["forwarders"] == 1
    assert data["webmail_url"] == "/webmail/"

    maps = write_mail_maps()
    assert (maps / "vmailbox").exists()
    assert "info@example.test" in (maps / "vmailbox").read_text(encoding="utf-8")
    assert "info@example.test" in (maps / "dovecot-users").read_text(encoding="utf-8")
    assert "$6$" in (maps / "dovecot-users").read_text(encoding="utf-8")
    assert "sales@example.test" in (maps / "valiases").read_text(encoding="utf-8")

    box_obj = Mailbox.objects.get(pk=box.json()["data"]["id"])
    assert box_obj.password_secret
    assert box_obj.get_password_plain() == "MailPass123!"

    sso = api.post(
        reverse("email-webmail-sso"),
        {"mailbox_id": box_obj.pk},
        format="json",
    )
    assert sso.status_code == 200
    assert "vzone-sso.php?t=" in sso.json()["data"]["url"]
    assert sso.json()["data"]["address"] == "info@example.test"


@pytest.mark.integration
@pytest.mark.django_db
def test_suspend_and_dkim(api: APIClient, mail_root):
    user = UserFactory(username="mail2")
    md = create_mail_domain(owner=user, name="dkim.test", enable_dns=True)
    box = create_mailbox(mail_domain=md, local_part="hello", password="MailPass123!")
    api.force_authenticate(user=user)

    suspend = api.post(
        reverse("email-mailbox-suspend", kwargs={"pk": box.pk}),
        {"suspended": True},
        format="json",
    )
    assert suspend.status_code == 200
    assert suspend.json()["data"]["status"] == "suspended"

    dkim = api.post(reverse("email-dkim", kwargs={"pk": md.pk}), {"selector": "mail"}, format="json")
    assert dkim.status_code == 200
    assert dkim.json()["data"]["dkim_enabled"] is True
    assert dkim.json()["data"]["dkim_selector"] == "mail"
    assert dkim.json()["data"]["dkim_public_key"]

    md.refresh_from_db()
    assert md.dkim_private_key.startswith("-----BEGIN")


@pytest.mark.integration
@pytest.mark.django_db
def test_email_quota(api: APIClient, mail_root):
    user = UserFactory(username="mail3")
    user.quota.emails = 1
    user.quota.save()
    md = create_mail_domain(owner=user, name="quota.test", enable_dns=False)
    create_mailbox(mail_domain=md, local_part="one", password="MailPass123!")
    api.force_authenticate(user=user)
    second = api.post(
        reverse("email-mailbox-list"),
        {"mail_domain_id": md.pk, "local_part": "two", "password": "MailPass123!"},
        format="json",
    )
    assert second.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_enable_dkim_writes_keys(mail_root):
    user = UserFactory(username="mail4")
    md = create_mail_domain(owner=user, name="keys.test", enable_dns=False)
    enable_dkim(md, selector="default")
    key_file = mail_root / "dkim" / "keys.test" / "default.private"
    assert key_file.exists()
    assert MailDomain.objects.get(pk=md.pk).dkim_enabled
    assert Mailbox.objects.count() == 0
    assert MailForwarder.objects.count() == 0
