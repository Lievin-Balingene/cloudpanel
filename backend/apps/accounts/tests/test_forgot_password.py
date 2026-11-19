"""Tests flux mot de passe oublié (anti-énumération + token/code)."""
from __future__ import annotations

import re

import pytest
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.forgot_password import _pepper_hash
from apps.accounts.models import PasswordResetChallenge
from apps.accounts.factories import AdminFactory, UserFactory


@pytest.mark.django_db
def test_forgot_password_anti_enumeration(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    api = APIClient()
    url = reverse("auth-forgot-password")

    unknown = api.post(url, {"identifier": "nobody-exists@example.com"}, format="json")
    assert unknown.status_code == 200
    assert "e-mail" in unknown.json()["data"]["detail"].lower() or "email" in unknown.json()["data"]["detail"].lower()
    assert len(mail.outbox) == 0

    user = UserFactory(password="OldPassword123!", email="real@example.com")
    known = api.post(url, {"identifier": user.email}, format="json")
    assert known.status_code == 200
    assert known.json()["data"]["detail"] == unknown.json()["data"]["detail"]
    assert len(mail.outbox) == 1
    assert PasswordResetChallenge.objects.filter(user=user, consumed_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_forgot_password_confirm_requires_code_and_revokes(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    api = APIClient()
    user = AdminFactory(password="OldPassword123!", email="admin-reset@example.com")

    req = api.post(
        reverse("auth-forgot-password"),
        {"identifier": user.username, "portal": "admin"},
        format="json",
    )
    assert req.status_code == 200
    assert len(mail.outbox) == 1
    body = mail.outbox[0].body
    token_m = re.search(r"token=([A-Za-z0-9_\-]+)", body)
    code_m = re.search(r"RESET-CODE:\s*([A-Z0-9]{4}-[A-Z0-9]{4})", body)
    assert token_m and code_m, body
    token = token_m.group(1)
    code = code_m.group(1)

    bad = api.post(
        reverse("auth-forgot-password-confirm"),
        {
            "token": token,
            "code": "AAAA-AAAA",
            "new_password": "BrandNewPass99!",
            "confirm_password": "BrandNewPass99!",
        },
        format="json",
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "forgot_password_bad_code"

    ok = api.post(
        reverse("auth-forgot-password-confirm"),
        {
            "token": token,
            "code": code,
            "new_password": "BrandNewPass99!",
            "confirm_password": "BrandNewPass99!",
        },
        format="json",
    )
    assert ok.status_code == 200
    user.refresh_from_db()
    assert user.check_password("BrandNewPass99!")
    assert user.must_change_password is False
    challenge = PasswordResetChallenge.objects.get(token_hash=_pepper_hash(token))
    assert challenge.consumed_at is not None

    reuse = api.post(
        reverse("auth-forgot-password-confirm"),
        {
            "token": token,
            "code": code,
            "new_password": "AnotherNewPass99!",
            "confirm_password": "AnotherNewPass99!",
        },
        format="json",
    )
    assert reuse.status_code == 400


@pytest.mark.django_db
def test_forgot_password_disabled_by_tweak(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    from apps.server_setup.models import ServerSetup

    setup = ServerSetup.get_solo()
    tweaks = dict(setup.tweak_settings or {})
    tweaks["allow_forgot_password"] = False
    setup.tweak_settings = tweaks
    setup.save(update_fields=["tweak_settings", "updated_at"])

    api = APIClient()
    res = api.post(
        reverse("auth-forgot-password"),
        {"identifier": "admin"},
        format="json",
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "forgot_password_disabled"
