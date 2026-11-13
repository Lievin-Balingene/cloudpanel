"""Tests Contact Manager WHM (notices email)."""
from __future__ import annotations

import pytest
from django.core import mail

from apps.accounts.models import User
from apps.server_setup.contact_notify import (
    EVENT_ACCOUNT_CREATION,
    get_contact_email,
    is_event_enabled,
    notify_account_creation,
)
from apps.server_setup.models import ServerSetup


@pytest.mark.django_db
def test_get_contact_email_from_setup():
    setup = ServerSetup.get_solo()
    setup.contact_email = "ops@example.com"
    setup.save(update_fields=["contact_email"])
    assert get_contact_email() == "ops@example.com"


@pytest.mark.django_db
def test_get_contact_email_falls_back_to_admin():
    setup = ServerSetup.get_solo()
    setup.contact_email = ""
    setup.save(update_fields=["contact_email"])
    User.objects.create_user(
        email="admin@example.com",
        username="admin",
        password="TestPass123!",
        role=User.Role.ADMINISTRATOR,
        is_staff=True,
    )
    assert get_contact_email() == "admin@example.com"
    setup.refresh_from_db()
    assert setup.contact_email == "admin@example.com"


@pytest.mark.django_db
def test_notify_account_creation_sends_cpanel_style_mail(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    setup = ServerSetup.get_solo()
    setup.contact_email = "ops@example.com"
    setup.hostname = "server.example.com"
    setup.tweak_settings = {EVENT_ACCOUNT_CREATION: True}
    setup.save()

    client = User.objects.create_user(
        email="client@example.com",
        username="cslared1",
        password="TestPass123!",
        role=User.Role.CLIENT,
        home_directory="/home/cslared1",
    )
    actor = User.objects.create_user(
        email="admin@example.com",
        username="vzone2432",
        password="TestPass123!",
        role=User.Role.ADMINISTRATOR,
        is_staff=True,
    )

    assert notify_account_creation(client, actor=actor, package_name="vzone2432_pro") is True
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["ops@example.com"]
    assert "Account Creation" in msg.subject
    assert "cslared1" in msg.body
    assert "***HIDDEN***" in msg.body
    assert "vzone2432_pro" in msg.body
    assert "vzone2432" in msg.body
    assert "Do not reply" in msg.body


@pytest.mark.django_db
def test_notify_disabled_by_tweak():
    setup = ServerSetup.get_solo()
    setup.contact_email = "ops@example.com"
    setup.tweak_settings = {EVENT_ACCOUNT_CREATION: False}
    setup.save()
    assert is_event_enabled(EVENT_ACCOUNT_CREATION) is False
    client = User.objects.create_user(
        email="c2@example.com",
        username="c2user",
        password="TestPass123!",
        role=User.Role.CLIENT,
    )
    assert notify_account_creation(client) is False
    assert len(mail.outbox) == 0
