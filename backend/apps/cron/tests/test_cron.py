"""Tests Cron Jobs."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.cron.models import CronJob
from apps.cron.services import build_cron_d_content, create_cron_job


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def cron_settings(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_CRON_JOBS_DIR = str(tmp_path / "cron" / "jobs")
    settings.VZONE_CRON_PROVISION_MODE = "mock"
    settings.VZONE_LINUX_USER_PROVISION = "mock"
    return settings


@pytest.mark.django_db
def test_create_cron_job_common_preset(cron_settings):
    user = UserFactory(username="cronuser", system_username="cronuser")
    job = create_cron_job(
        owner=user,
        command="/usr/bin/php -q public_html/cron.php",
        common="once_per_five",
        label="php cron",
    )
    assert job.minute == "*/5"
    assert job.hour == "*"
    assert CronJob.objects.filter(owner=user).count() == 1
    text = build_cron_d_content(user, [job])
    assert "VZONE_ID=" in text
    assert "cronuser" in text
    assert "public_html/cron.php" in text


@pytest.mark.django_db
def test_cron_api_list_create(api: APIClient, cron_settings):
    user = UserFactory(username="cronapi", system_username="cronapi")
    api.force_authenticate(user=user)
    created = api.post(
        reverse("cron-job-list"),
        {
            "common": "once_per_day",
            "command": "echo hello",
            "email_to": "owner@example.com",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    listed = api.get(reverse("cron-job-list"))
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1
