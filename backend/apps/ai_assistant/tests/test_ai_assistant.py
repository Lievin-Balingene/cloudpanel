"""Tests assistant IA déploiement."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.ai_assistant.services.redaction import redact_text
from apps.ai_assistant.tools import ensure_tools_loaded, get_tool


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def test_redact_secrets():
    text = "password=SuperSecret123 token=abc DATABASE_URL=postgres://u:p@h/db"
    out = redact_text(text)
    assert "SuperSecret123" not in out
    assert "REDACTED" in out


@pytest.mark.django_db
def test_tools_whitelist_loaded():
    ensure_tools_loaded()
    assert get_tool("get_server_info") is not None
    assert get_tool("restart_application") is not None
    assert get_tool("restart_application").dangerous is True
    assert get_tool("rm_rf") is None


@pytest.mark.django_db
def test_ai_conversation_flow(api: APIClient, settings):
    settings.VZONE_AI_PROVIDER = "mock"
    user = UserFactory(username="aideploy", password="TestPassword123!")
    api.force_authenticate(user=user)

    created = api.post(reverse("ai-conversation-list"), {}, format="json")
    assert created.status_code == 201
    pk = created.json()["data"]["id"]

    status = api.get(reverse("ai-status"))
    assert status.status_code == 200
    assert status.json()["data"]["provider"] == "mock"
    tools = {t["name"] for t in status.json()["data"]["tools"]}
    assert "get_deployment_logs" in tools
    assert "deploy_application" in tools
    assert "create_python_app_from_git" in tools

    books = api.get(reverse("ai-playbooks"))
    assert books.status_code == 200
    assert any(p["id"] == "django-github" for p in books.json()["data"])

    msg = api.post(
        reverse("ai-conversation-message", kwargs={"pk": pk}),
        {"message": "Je veux déployer mon application Django depuis GitHub"},
        format="json",
    )
    assert msg.status_code == 200
    data = msg.json()["data"]
    assert data["message"]["role"] == "assistant"
    assert data["message"]["content"]
    assert data["provider"] == "mock"
