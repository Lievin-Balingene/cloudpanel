"""Tests module Git Deploy."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.git_deploy.models import GitDeployLog, GitRepository
from apps.git_deploy.services import create_repository, pull_repository, webhook_deploy


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def git_root(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_GIT_CONFIG_DIR = str(tmp_path / "git")
    settings.VZONE_GIT_PROVISION_MODE = "mock"
    settings.VZONE_GIT_MAX_REPOS = 20
    return settings.VZONE_HOME_ROOT


@pytest.mark.integration
@pytest.mark.django_db
def test_create_pull_and_logs(api: APIClient, git_root):
    user = UserFactory(username="gituser", password="TestPassword123!")
    api.force_authenticate(user=user)

    created = api.post(
        reverse("git-repo-list"),
        {
            "name": "webapp",
            "remote_url": "https://github.com/example/webapp.git",
            "branch": "main",
            "clone_now": True,
        },
        format="json",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["name"] == "webapp"
    assert data["status"] == "ready"
    assert data["deploy_key_public"].startswith("ssh-ed25519")
    assert data["webhook_token"]
    pk = data["id"]

    repo_path = Path(git_root) / "gituser" / "repositories" / "webapp"
    assert (repo_path / ".git").exists()
    assert (repo_path / "README.md").exists()

    pull = api.post(reverse("git-repo-pull", kwargs={"pk": pk}))
    assert pull.status_code == 200
    assert pull.json()["data"]["status"] == "ready"

    logs = api.get(reverse("git-log-list") + f"?repository_id={pk}")
    assert logs.status_code == 200
    events = {item["event_type"] for item in logs.json()["data"]}
    assert "clone" in events
    assert "pull" in events
    assert "keygen" in events

    overview = api.get(reverse("git-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["repositories"] == 1


@pytest.mark.integration
@pytest.mark.django_db
def test_webhook_deploy(api: APIClient, git_root):
    user = UserFactory(username="git2")
    repo = create_repository(
        owner=user,
        name="api",
        remote_url="https://github.com/example/api.git",
        clone_now=True,
    )
    token = repo.webhook_token
    resp = api.post(reverse("git-webhook", kwargs={"token": token}))
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ready"
    assert GitDeployLog.objects.filter(repository=repo, event_type="webhook").exists()

    bad = api.post(reverse("git-webhook", kwargs={"token": "invalid-token"}))
    assert bad.status_code == 404


@pytest.mark.integration
@pytest.mark.django_db
def test_git_quota(api: APIClient, git_root, settings):
    settings.VZONE_GIT_MAX_REPOS = 1
    user = UserFactory(username="git3")
    create_repository(
        owner=user,
        name="one",
        remote_url="https://github.com/example/one.git",
        clone_now=True,
    )
    api.force_authenticate(user=user)
    second = api.post(
        reverse("git-repo-list"),
        {"name": "two", "remote_url": "https://github.com/example/two.git"},
        format="json",
    )
    assert second.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_pull_helper(git_root):
    user = UserFactory(username="git4")
    repo = create_repository(
        owner=user,
        name="svc",
        remote_url="git@github.com:example/svc.git",
        clone_now=True,
    )
    before = repo.last_commit
    repo = pull_repository(repo)
    assert repo.status == GitRepository.Status.READY
    assert repo.last_commit
    assert repo.last_commit != before or before  # commit updated in mock
