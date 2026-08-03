"""Tests module Backups."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.backups.models import BackupArchive, BackupEventLog, BackupSchedule
from apps.backups.services import create_backup, restore_backup, upsert_schedule
from apps.packages.models import HostingPackage, PackageAssignment


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def backup_root(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_BACKUP_DIR = str(tmp_path / "backups")
    settings.VZONE_BACKUP_PROVISION_MODE = "mock"
    settings.VZONE_BACKUP_MAX = 5
    return settings.VZONE_HOME_ROOT


def _disable_backup(user):
    pkg = HostingPackage.objects.create(
        name=f"nobackup-{user.username}",
        allow_backup=False,
    )
    PackageAssignment.objects.create(user=user, package=pkg)


@pytest.mark.integration
@pytest.mark.django_db
def test_create_restore_delete_backup(api: APIClient, backup_root):
    user = UserFactory(username="bkuser", password="TestPassword123!")
    api.force_authenticate(user=user)

    created = api.post(
        reverse("backup-archive-list"),
        {"backup_type": "full", "label": "Première"},
        format="json",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["status"] == "completed"
    assert data["includes"] == ["home", "databases", "email"]
    assert data["size_bytes"] > 0
    assert data["checksum"]
    pk = data["id"]

    restore = api.post(reverse("backup-archive-restore", kwargs={"pk": pk}))
    assert restore.status_code == 200
    assert restore.json()["data"]["status"] == "restored"

    download = api.get(reverse("backup-archive-download", kwargs={"pk": pk}))
    assert download.status_code == 200
    assert download.json()["data"]["exists"] is True

    overview = api.get(reverse("backup-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["archives"] == 1

    deleted = api.delete(reverse("backup-archive-detail", kwargs={"pk": pk}))
    assert deleted.status_code == 204
    assert BackupArchive.objects.count() == 0


@pytest.mark.integration
@pytest.mark.django_db
def test_backup_disabled_by_package(api: APIClient, backup_root):
    user = UserFactory(username="bkdeny")
    _disable_backup(user)
    api.force_authenticate(user=user)
    resp = api.post(
        reverse("backup-archive-list"),
        {"backup_type": "home"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.django_db
def test_backup_quota_limit(api: APIClient, backup_root, settings):
    settings.VZONE_BACKUP_MAX = 1
    user = UserFactory(username="bkquota")
    create_backup(owner=user, backup_type="home", name="one")
    api.force_authenticate(user=user)
    second = api.post(
        reverse("backup-archive-list"),
        {"backup_type": "home", "name": "two"},
        format="json",
    )
    assert second.status_code == 403


@pytest.mark.integration
@pytest.mark.django_db
def test_backup_schedule(api: APIClient, backup_root):
    user = UserFactory(username="bksched")
    api.force_authenticate(user=user)
    created = api.post(
        reverse("backup-schedule-list"),
        {
            "frequency": "daily",
            "hour": 3,
            "includes": ["home", "databases"],
            "is_active": True,
        },
        format="json",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["frequency"] == "daily"
    assert data["hour"] == 3
    assert BackupSchedule.objects.filter(owner=user).count() == 1

    listed = api.get(reverse("backup-schedule-list"))
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1


@pytest.mark.unit
@pytest.mark.django_db
def test_helpers(backup_root):
    user = UserFactory(username="bkhelp")
    archive = create_backup(owner=user, name="help1", backup_type="home")
    assert archive.status == BackupArchive.Status.COMPLETED
    archive = restore_backup(archive)
    assert archive.status == BackupArchive.Status.RESTORED
    schedule = upsert_schedule(owner=user, frequency="weekly", hour=4)
    assert schedule.frequency == "weekly"
    assert BackupEventLog.objects.filter(owner=user).count() >= 2
