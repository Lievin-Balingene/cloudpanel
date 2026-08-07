"""Tests unitaires moteur backup (Restic/Rclone wrappers + service mock)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.backups.engine import CmdResult, run_cmd
from apps.backups.engine.providers import build_rclone_section, provider_path
from apps.backups.engine.restic import SnapshotInfo, _parse_backup_json, generate_password
from apps.backups.models import BackupArchive, BackupDestination, BackupEventLog, BackupSchedule
from apps.backups.services import (
    apply_retention,
    create_backup,
    create_destination,
    overview_for,
    restore_backup,
    upsert_schedule,
)
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


# ----- engine unit -----


@pytest.mark.unit
def test_run_cmd_missing_binary():
    result = run_cmd(["__vzone_no_such_bin_xyz__"], timeout=5)
    assert result.returncode == 127
    assert not result.ok


@pytest.mark.unit
def test_provider_sections():
    s3 = build_rclone_section(
        "s3",
        "mys3",
        {"endpoint": "https://s3.example", "region": "eu"},
        {"access_key_id": "AK", "secret_access_key": "SK"},
    )
    assert "type = s3" in s3
    assert "access_key_id = AK" in s3
    assert provider_path("s3", {"bucket": "bk", "prefix": "p"}) == "bk/p"

    r2 = build_rclone_section(
        "r2",
        "myr2",
        {"account_id": "abc"},
        {"access_key_id": "A", "secret_access_key": "S"},
    )
    assert "Cloudflare" in r2
    assert "abc.r2.cloudflarestorage.com" in r2

    local = build_rclone_section("local", "loc", {"path": "/data"}, {})
    assert "type = local" in local


@pytest.mark.unit
def test_parse_restic_summary_json():
    stdout = (
        '{"message_type":"status","percent_done":0.5}\n'
        '{"message_type":"summary","snapshot_id":"deadbeefcafebabe",'
        '"data_added":1234,"files_new":2,"files_changed":1,"files_unmodified":9}\n'
    )
    snap = _parse_backup_json(stdout)
    assert snap is not None
    assert snap.id == "deadbeefcafebabe"
    assert snap.summary["data_added"] == 1234
    assert generate_password()


@pytest.mark.unit
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
    assert data["snapshot_id"]
    assert data["progress"] == 100
    pk = data["id"]

    restore = api.post(reverse("backup-archive-restore", kwargs={"pk": pk}))
    assert restore.status_code == 200
    assert restore.json()["data"]["status"] == "restored"

    download = api.get(reverse("backup-archive-download", kwargs={"pk": pk}))
    assert download.status_code == 200
    assert download.json()["data"]["exists"] is True
    assert download.json()["data"]["engine"] == "restic"

    overview = api.get(reverse("backup-overview"))
    assert overview.status_code == 200
    body = overview.json()["data"]
    assert body["archives"] == 1
    assert body["engine"] == "restic"

    deleted = api.delete(reverse("backup-archive-detail", kwargs={"pk": pk}))
    assert deleted.status_code == 204
    assert BackupArchive.objects.count() == 0


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
@pytest.mark.django_db
def test_backup_schedule_hourly_retention(api: APIClient, backup_root):
    user = UserFactory(username="bksched")
    api.force_authenticate(user=user)
    created = api.post(
        reverse("backup-schedule-list"),
        {
            "frequency": "hourly",
            "minute": 15,
            "includes": ["home", "databases"],
            "is_active": True,
            "keep_daily": 14,
            "keep_weekly": 8,
            "keep_monthly": 12,
        },
        format="json",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["frequency"] == "hourly"
    assert data["keep_daily"] == 14
    assert BackupSchedule.objects.filter(owner=user).count() == 1


@pytest.mark.unit
@pytest.mark.django_db
def test_destination_local_mock(api: APIClient, backup_root):
    user = UserFactory(username="bkdest")
    api.force_authenticate(user=user)
    resp = api.post(
        reverse("backup-destination-list"),
        {"name": "mylocal", "provider": "local", "is_default": True},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["provider"] == "local"
    assert BackupDestination.objects.filter(owner=user, name="mylocal").exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_live_restore_extracts_into_account_home(backup_root, settings, tmp_path):
    settings.VZONE_BACKUP_PROVISION_MODE = "live"
    user = UserFactory(username="bklive")
    user.system_username = "bklive"
    user.save(update_fields=["system_username"])
    home = backup_root / "bklive"
    home.mkdir(parents=True, exist_ok=True)
    (home / "public_html").mkdir()
    (home / "public_html" / "index.html").write_text("hello-backup", encoding="utf-8")

    archive = create_backup(owner=user, name="live1", backup_type="home", async_run=False)
    assert archive.status == BackupArchive.Status.COMPLETED
    assert archive.size_bytes > 0

    (home / "public_html" / "index.html").unlink()
    (home / "public_html" / "gone.txt").write_text("should-remain-or-overwrite", encoding="utf-8")

    restored = restore_backup(archive)
    assert restored.status == BackupArchive.Status.RESTORED
    assert (home / "public_html" / "index.html").read_text(encoding="utf-8") == "hello-backup"
    assert not (backup_root / "home" / "public_html" / "index.html").exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_helpers_and_retention_mock(backup_root):
    user = UserFactory(username="bkhelp")
    archive = create_backup(owner=user, name="help1", backup_type="home")
    assert archive.status == BackupArchive.Status.COMPLETED
    archive = restore_backup(archive)
    assert archive.status == BackupArchive.Status.RESTORED
    schedule = upsert_schedule(owner=user, frequency="weekly", hour=4, keep_daily=3)
    assert schedule.frequency == "weekly"
    assert schedule.keep_daily == 3
    assert BackupEventLog.objects.filter(owner=user).count() >= 2
    ov = overview_for(user)
    assert ov["engine"] == "restic"
    dest = archive.destination or create_destination(
        actor=user, name="retlocal", provider="local", owner=user
    )
    result = apply_retention(destination=dest, owner=user, keep_daily=3)
    assert result.get("mock") is True


@pytest.mark.unit
@pytest.mark.django_db
@patch("apps.backups.engine.restic.backup_paths")
@patch("apps.backups.engine.restic.init_repository")
def test_restic_backup_service_mocked(mock_init, mock_backup, backup_root, settings):
    settings.VZONE_BACKUP_PROVISION_MODE = "live"
    mock_init.return_value = CmdResult(returncode=0, stdout="created")
    mock_backup.return_value = (
        CmdResult(returncode=0, stdout='{"message_type":"summary","snapshot_id":"abc123","data_added":99}\n'),
        SnapshotInfo(id="abc123", summary={"data_added": 99, "files_new": 1}),
    )
    user = UserFactory(username="bkrestic")
    user.system_username = "bkrestic"
    user.save(update_fields=["system_username"])
    (backup_root / "bkrestic" / "public_html").mkdir(parents=True)

    with patch("shutil.which", return_value="/usr/bin/restic"):
        archive = create_backup(
            owner=user, name="r1", backup_type="home", async_run=False
        )
    assert archive.status == BackupArchive.Status.COMPLETED
    assert archive.snapshot_id == "abc123"
    assert archive.size_bytes == 99
    mock_backup.assert_called_once()
