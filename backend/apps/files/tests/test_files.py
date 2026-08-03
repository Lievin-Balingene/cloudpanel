"""Tests File Manager."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.core.exceptions import VZoneAPIException
from apps.files import services


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def user_home(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    return settings.VZONE_HOME_ROOT


@pytest.mark.integration
@pytest.mark.django_db
def test_list_mkdir_upload_download(api: APIClient, user_home):
    user = UserFactory(username="fmuser", password="TestPassword123!")
    api.force_authenticate(user=user)

    listing = api.get(reverse("files-list"))
    assert listing.status_code == 200
    assert "public_html" in {e["name"] for e in listing.json()["data"]["entries"]}

    mkdir = api.post(reverse("files-mkdir"), {"path": "", "name": "docs"}, format="json")
    assert mkdir.status_code == 201

    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = api.post(
        reverse("files-upload"),
        {
            "path": "docs",
            "file": SimpleUploadedFile("hello.txt", b"hello vzone", content_type="text/plain"),
        },
        format="multipart",
    )
    assert upload.status_code == 201
    assert upload.json()["data"]["name"] == "hello.txt"

    download = api.get(reverse("files-download"), {"path": "docs/hello.txt"})
    assert download.status_code == 200
    assert b"hello vzone" in b"".join(download.streaming_content)


@pytest.mark.integration
@pytest.mark.django_db
def test_copy_move_compress_decompress(api: APIClient, user_home):
    user = UserFactory(username="fmops", password="TestPassword123!")
    api.force_authenticate(user=user)
    home = services.user_home(user)
    (home / "public_html" / "a.txt").write_text("alpha", encoding="utf-8")

    copy = api.post(
        reverse("files-copy"),
        {"paths": ["public_html/a.txt"], "destination": "tmp"},
        format="json",
    )
    assert copy.status_code == 200
    assert (home / "tmp" / "a.txt").exists()

    compress = api.post(
        reverse("files-compress"),
        {
            "paths": ["tmp/a.txt"],
            "archive": "tmp/archive.zip",
            "format": "zip",
        },
        format="json",
    )
    assert compress.status_code == 201
    assert zipfile.is_zipfile(home / "tmp" / "archive.zip")

    (home / "tmp" / "out").mkdir()
    decompress = api.post(
        reverse("files-decompress"),
        {"archive": "tmp/archive.zip", "destination": "tmp/out"},
        format="json",
    )
    assert decompress.status_code == 200
    assert (home / "tmp" / "out" / "a.txt").exists()


@pytest.mark.integration
@pytest.mark.django_db
def test_editor_and_chmod_and_search(api: APIClient, user_home):
    user = UserFactory(username="fmedit", password="TestPassword123!")
    api.force_authenticate(user=user)
    create = api.post(
        reverse("files-create"),
        {"path": "public_html", "name": "index.html", "content": "<h1>Hi</h1>"},
        format="json",
    )
    assert create.status_code == 201

    read = api.get(reverse("files-read"), {"path": "public_html/index.html"})
    assert read.status_code == 200
    assert "<h1>Hi</h1>" in read.json()["data"]["content"]

    write = api.put(
        reverse("files-write"),
        {"path": "public_html/index.html", "content": "<h1>V-zone</h1>"},
        format="json",
    )
    assert write.status_code == 200

    chmod = api.post(
        reverse("files-chmod"),
        {"path": "public_html/index.html", "mode": "644"},
        format="json",
    )
    assert chmod.status_code == 200

    search = api.get(reverse("files-search"), {"query": "index", "path": ""})
    assert search.status_code == 200
    assert any(item["name"] == "index.html" for item in search.json()["data"])


@pytest.mark.unit
@pytest.mark.django_db
def test_path_traversal_blocked(user_home):
    user = UserFactory(username="fmsec")
    with pytest.raises(VZoneAPIException):
        services.resolve_path(user, "../etc/passwd")
