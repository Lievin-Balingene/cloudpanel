"""Tests module bases de données."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.databases.models import Database, DatabasePrivilege, DatabaseUser
from apps.databases.services import create_database, create_database_user, grant_privilege


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def db_root(tmp_path, settings):
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DB_MAPS_DIR = str(tmp_path / "databases")
    settings.VZONE_DB_PROVISION_MODE = "mock"
    settings.VZONE_PHPMYADMIN_URL = "/phpmyadmin/"
    settings.VZONE_PGADMIN_URL = "/pgadmin/"
    return Path(settings.VZONE_DB_MAPS_DIR)


@pytest.mark.integration
@pytest.mark.django_db
def test_create_database_user_and_grant(api: APIClient, db_root):
    user = UserFactory(username="site1", password="TestPassword123!")
    api.force_authenticate(user=user)

    create_db = api.post(
        reverse("databases-list"),
        {"name": "app", "engine": "mysql"},
        format="json",
    )
    assert create_db.status_code == 201
    data = create_db.json()["data"]
    assert data["name"] == "site1_app"
    assert data["engine"] == "mysql"
    db_id = data["id"]

    create_user = api.post(
        reverse("databases-user-list"),
        {"username": "app", "password": "DbPass123!", "engine": "mysql"},
        format="json",
    )
    assert create_user.status_code == 201
    assert create_user.json()["data"]["username"] == "site1_app"
    user_id = create_user.json()["data"]["id"]

    grant = api.post(
        reverse("databases-privilege-list"),
        {"database_id": db_id, "user_id": user_id, "privileges": "ALL"},
        format="json",
    )
    assert grant.status_code == 201

    overview = api.get(reverse("databases-overview"))
    assert overview.status_code == 200
    ov = overview.json()["data"]
    assert ov["databases"] == 1
    assert ov["users"] == 1
    assert ov["privileges"] == 1
    assert ov["phpmyadmin_url"] == "/phpmyadmin/"

    pending = list((db_root / "pending").glob("*.sql"))
    assert len(pending) >= 3
    assert (db_root / "inventory.txt").exists()


@pytest.mark.integration
@pytest.mark.django_db
def test_postgresql_and_delete(api: APIClient, db_root):
    user = UserFactory(username="site2")
    api.force_authenticate(user=user)
    created = api.post(
        reverse("databases-list"),
        {"name": "cms", "engine": "postgresql"},
        format="json",
    )
    assert created.status_code == 201
    assert created.json()["data"]["name"] == "site2_cms"
    pk = created.json()["data"]["id"]
    deleted = api.delete(reverse("databases-detail", kwargs={"pk": pk}))
    assert deleted.status_code == 204
    assert Database.objects.count() == 0


@pytest.mark.integration
@pytest.mark.django_db
def test_database_quota(api: APIClient, db_root):
    user = UserFactory(username="site3")
    user.quota.databases = 1
    user.quota.save()
    create_database(owner=user, name="one", engine="mysql")
    api.force_authenticate(user=user)
    second = api.post(
        reverse("databases-list"),
        {"name": "two", "engine": "mysql"},
        format="json",
    )
    assert second.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_grant_helper(db_root):
    user = UserFactory(username="site4")
    db = create_database(owner=user, name="shop", engine="mysql")
    db_user = create_database_user(owner=user, username="shop", password="DbPass123!")
    priv = grant_privilege(database=db, user=db_user, privileges="READ")
    assert isinstance(priv, DatabasePrivilege)
    assert DatabaseUser.objects.filter(username="site4_shop").exists()
