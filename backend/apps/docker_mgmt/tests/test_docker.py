"""Tests module Docker."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.docker_mgmt.models import DockerContainer, DockerContainerLog
from apps.docker_mgmt.services import create_container, start_container, stop_container


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def docker_root(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DOCKER_CONFIG_DIR = str(tmp_path / "docker")
    settings.VZONE_DOCKER_PROVISION_MODE = "mock"
    return settings.VZONE_HOME_ROOT


def _enable_docker(user, limit: int = 5):
    user.quota.docker_containers = limit
    user.quota.save()


@pytest.mark.integration
@pytest.mark.django_db
def test_create_start_stop_container(api: APIClient, docker_root):
    user = UserFactory(username="dockuser", password="TestPassword123!")
    _enable_docker(user)
    api.force_authenticate(user=user)

    created = api.post(
        reverse("docker-container-list"),
        {
            "name": "web",
            "image": "nginx",
            "tag": "alpine",
            "ports": {"8080": "80"},
            "start_now": True,
        },
        format="json",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["name"] == "web"
    assert data["image_ref"] == "nginx:alpine"
    assert data["status"] == "running"
    assert data["container_id"]
    pk = data["id"]

    stop = api.post(reverse("docker-container-stop", kwargs={"pk": pk}))
    assert stop.status_code == 200
    assert stop.json()["data"]["status"] == "stopped"

    start = api.post(reverse("docker-container-start", kwargs={"pk": pk}))
    assert start.status_code == 200
    assert start.json()["data"]["status"] == "running"

    logs = api.get(reverse("docker-container-logs", kwargs={"pk": pk}))
    assert logs.status_code == 200
    assert "mock start" in logs.json()["data"]["logs"]

    overview = api.get(reverse("docker-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["containers"] == 1


@pytest.mark.integration
@pytest.mark.django_db
def test_docker_quota_zero(api: APIClient, docker_root):
    user = UserFactory(username="dock2")
    # default docker_containers = 0
    api.force_authenticate(user=user)
    resp = api.post(
        reverse("docker-container-list"),
        {"name": "denied", "image": "alpine"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.django_db
def test_docker_quota_limit(api: APIClient, docker_root):
    user = UserFactory(username="dock3")
    _enable_docker(user, limit=1)
    create_container(owner=user, name="one", image="alpine", start_now=True)
    api.force_authenticate(user=user)
    second = api.post(
        reverse("docker-container-list"),
        {"name": "two", "image": "alpine"},
        format="json",
    )
    assert second.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_helpers(docker_root):
    user = UserFactory(username="dock4")
    _enable_docker(user)
    c = create_container(owner=user, name="svc", image="redis", start_now=False)
    assert c.status == DockerContainer.Status.CREATED
    c = start_container(c)
    assert c.status == DockerContainer.Status.RUNNING
    c = stop_container(c)
    assert c.status == DockerContainer.Status.STOPPED
    assert DockerContainerLog.objects.filter(container=c).count() >= 2
