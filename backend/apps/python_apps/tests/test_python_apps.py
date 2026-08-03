"""Tests module applications Python."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.python_apps.models import PythonApp
from apps.python_apps.services import create_python_app, start_python_app, stop_python_app


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def py_root(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_PYTHON_CONFIG_DIR = str(tmp_path / "python_apps")
    settings.VZONE_PYTHON_PROVISION_MODE = "mock"
    settings.VZONE_PYTHON_PORT_BASE = 8100
    return settings.VZONE_HOME_ROOT


@pytest.mark.integration
@pytest.mark.django_db
def test_create_start_stop_python_app(api: APIClient, py_root):
    user = UserFactory(username="pyuser", password="TestPassword123!")
    api.force_authenticate(user=user)

    created = api.post(
        reverse("python-app-list"),
        {"name": "webapp", "mode": "wsgi", "framework": "django"},
        format="json",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["name"] == "webapp"
    assert data["relative_root"] == "apps/webapp"
    assert data["status"] == "stopped"
    assert data["port"] >= 8100
    pk = data["id"]

    app_path = Path(py_root) / "pyuser" / "apps" / "webapp"
    assert (app_path / "passenger_wsgi.py").exists()
    assert (app_path / ".venv" / "pyvenv.cfg").exists()

    start = api.post(reverse("python-app-start", kwargs={"pk": pk}))
    assert start.status_code == 200
    assert start.json()["data"]["status"] == "running"

    install = api.post(reverse("python-app-install", kwargs={"pk": pk}))
    assert install.status_code == 200

    logs = api.get(reverse("python-app-logs", kwargs={"pk": pk}))
    assert logs.status_code == 200
    assert "pip.log" in logs.json()["data"]

    stop = api.post(reverse("python-app-stop", kwargs={"pk": pk}))
    assert stop.status_code == 200
    assert stop.json()["data"]["status"] == "stopped"

    overview = api.get(reverse("python-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["apps"] == 1


@pytest.mark.integration
@pytest.mark.django_db
def test_asgi_and_delete(api: APIClient, py_root):
    user = UserFactory(username="py2")
    api.force_authenticate(user=user)
    created = api.post(
        reverse("python-app-list"),
        {"name": "api", "mode": "asgi", "framework": "fastapi"},
        format="json",
    )
    assert created.status_code == 201
    assert created.json()["data"]["entrypoint"] == "asgi:application"
    pk = created.json()["data"]["id"]
    assert (Path(py_root) / "py2" / "apps" / "api" / "asgi.py").exists()
    deleted = api.delete(reverse("python-app-detail", kwargs={"pk": pk}) + "?remove_files=true")
    assert deleted.status_code == 204
    assert PythonApp.objects.count() == 0


@pytest.mark.integration
@pytest.mark.django_db
def test_python_quota(api: APIClient, py_root):
    user = UserFactory(username="py3")
    user.quota.python_apps = 1
    user.quota.save()
    create_python_app(owner=user, name="one")
    api.force_authenticate(user=user)
    second = api.post(reverse("python-app-list"), {"name": "two"}, format="json")
    assert second.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_start_stop_helpers(py_root):
    user = UserFactory(username="py4")
    app = create_python_app(owner=user, name="svc", mode="wsgi")
    app = start_python_app(app)
    assert app.status == PythonApp.Status.RUNNING
    assert app.pid
    app = stop_python_app(app)
    assert app.status == PythonApp.Status.STOPPED
    assert app.pid is None
