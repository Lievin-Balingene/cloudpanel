"""Tests module applications Node.js."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.node_apps.models import NodeApp
from apps.node_apps.services import create_node_app, start_node_app, stop_node_app


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def node_root(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_NODE_CONFIG_DIR = str(tmp_path / "node_apps")
    settings.VZONE_NODE_PROVISION_MODE = "mock"
    settings.VZONE_NODE_PORT_BASE = 9100
    return settings.VZONE_HOME_ROOT


@pytest.mark.integration
@pytest.mark.django_db
def test_create_start_stop_node_app(api: APIClient, node_root):
    user = UserFactory(username="nodeuser", password="TestPassword123!")
    api.force_authenticate(user=user)

    created = api.post(
        reverse("node-app-list"),
        {"name": "api", "framework": "express"},
        format="json",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["name"] == "api"
    assert data["relative_root"] == "nodeapps/api"
    assert data["status"] == "stopped"
    assert data["port"] >= 9100
    pk = data["id"]

    app_path = Path(node_root) / "nodeuser" / "nodeapps" / "api"
    assert (app_path / "package.json").exists()
    assert (app_path / "server.js").exists()

    start = api.post(reverse("node-app-start", kwargs={"pk": pk}))
    assert start.status_code == 200
    assert start.json()["data"]["status"] == "running"

    install = api.post(reverse("node-app-install", kwargs={"pk": pk}))
    assert install.status_code == 200

    logs = api.get(reverse("node-app-logs", kwargs={"pk": pk}))
    assert logs.status_code == 200
    assert "npm.log" in logs.json()["data"]

    stop = api.post(reverse("node-app-stop", kwargs={"pk": pk}))
    assert stop.status_code == 200
    assert stop.json()["data"]["status"] == "stopped"

    overview = api.get(reverse("node-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["apps"] == 1


@pytest.mark.integration
@pytest.mark.django_db
def test_node_delete(api: APIClient, node_root):
    user = UserFactory(username="node2")
    api.force_authenticate(user=user)
    created = api.post(reverse("node-app-list"), {"name": "web"}, format="json")
    pk = created.json()["data"]["id"]
    deleted = api.delete(reverse("node-app-detail", kwargs={"pk": pk}) + "?remove_files=true")
    assert deleted.status_code == 204
    assert NodeApp.objects.count() == 0


@pytest.mark.integration
@pytest.mark.django_db
def test_node_quota(api: APIClient, node_root):
    user = UserFactory(username="node3")
    user.quota.node_apps = 1
    user.quota.save()
    create_node_app(owner=user, name="one")
    api.force_authenticate(user=user)
    second = api.post(reverse("node-app-list"), {"name": "two"}, format="json")
    assert second.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_start_stop_helpers(node_root):
    user = UserFactory(username="node4")
    app = create_node_app(owner=user, name="svc")
    app = start_node_app(app)
    assert app.status == NodeApp.Status.RUNNING
    assert app.pid
    app = stop_node_app(app)
    assert app.status == NodeApp.Status.STOPPED
    assert app.pid is None
