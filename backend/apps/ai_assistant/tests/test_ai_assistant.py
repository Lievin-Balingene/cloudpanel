"""Tests assistant IA déploiement."""
from __future__ import annotations

import json

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.ai_assistant.tools import ensure_tools_loaded, get_tool


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def test_page_context_normalize():
    from apps.ai_assistant.services.page_context import normalize_ui_context

    ui = normalize_ui_context({"path": "/panel/python"})
    assert ui["section"] == "python"
    assert "logs" in ui["need"].lower() or "Python" in ui["label"]


@pytest.mark.django_db
def test_jail_catalog_no_free_shell():
    from apps.ai_assistant.services.jail_commands import JAIL_COMMANDS, get_jail_command

    assert get_jail_command("rm_rf") is None
    assert "pwd" in JAIL_COMMANDS
    assert all(";" not in " ".join(m["argv"]) for m in JAIL_COMMANDS.values())


@pytest.mark.django_db
def test_tools_whitelist_loaded():
    ensure_tools_loaded()
    assert get_tool("get_server_info") is not None
    assert get_tool("restart_application") is not None
    assert get_tool("restart_application").dangerous is True
    assert get_tool("stop_application") is not None
    assert get_tool("stop_application").dangerous is True
    assert get_tool("start_application") is not None
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

    listed = api.post(
        reverse("ai-conversation-message", kwargs={"pk": pk}),
        {"message": "liste moi mes applications pythons"},
        format="json",
    )
    assert listed.status_code == 200
    body = listed.json()["data"]["message"]["content"].lower()
    assert "python" in body
    assert "que préfères-tu" not in body


def test_mock_list_apps_intent_calls_tool():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(
            name="check_application_status",
            description="statut",
            parameters={"type": "object", "properties": {}},
        )
    ]
    r = p.chat(
        [ChatMessage(role="user", content="liste moi mes applications pythons")],
        tools=tools,
    )
    assert r.tool_calls
    assert r.tool_calls[0].name == "check_application_status"


def test_mock_smalltalk_how_are_you():
    from apps.ai_assistant.providers import ChatMessage
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    r = p.chat(
        [
            ChatMessage(role="user", content="salut"),
            ChatMessage(role="assistant", content="Salut !"),
            ChatMessage(role="user", content="comment vas-tu"),
        ],
        tools=[],
    )
    assert not r.tool_calls
    low = r.content.lower()
    assert "ça va" in low or "ca va" in low
    assert "stoppe mon application" not in low


def test_mock_start_verb_and_history_id():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider, _lifecycle_verb

    assert _lifecycle_verb("demarre mon application python") == "start"
    assert _lifecycle_verb("démarre l'application") == "start"
    assert _lifecycle_verb("stoppe mon application") == "stop"
    assert _lifecycle_verb("redémarre l'app") == "restart"

    p = MockProvider()
    tools = [
        ToolSpec(
            name="start_application",
            description="start",
            parameters={"type": "object", "properties": {}},
            dangerous=True,
        ),
        ToolSpec(
            name="check_application_status",
            description="status",
            parameters={"type": "object", "properties": {}},
        ),
    ]
    r = p.chat(
        [
            ChatMessage(
                role="system",
                content='Contexte {"last_app": {"id": 7, "runtime": "python"}}',
            ),
            ChatMessage(
                role="assistant",
                content="Je prépare l'action pour **arrêter** `demo` (id 7, python).",
            ),
            ChatMessage(role="user", content="demarre mon application python"),
        ],
        tools=tools,
    )
    assert r.tool_calls
    assert r.tool_calls[0].name == "start_application"
    assert r.tool_calls[0].arguments.get("app_id") == 7


def test_mock_stop_intent_lists_then_stops():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(
            name="check_application_status",
            description="statut",
            parameters={"type": "object", "properties": {}},
        ),
        ToolSpec(
            name="stop_application",
            description="stop",
            parameters={"type": "object", "properties": {}},
            dangerous=True,
        ),
    ]
    r1 = p.chat(
        [ChatMessage(role="user", content="peux tu stopper mon application python??")],
        tools=tools,
    )
    assert r1.tool_calls
    assert r1.tool_calls[0].name == "check_application_status"

    status_payload = {
        "ok": True,
        "data": {
            "python_apps": [
                {"id": 7, "name": "demo", "status": "running", "port": 8001, "domain": "x.test"}
            ],
            "node_apps": [],
        },
    }
    r2 = p.chat(
        [
            ChatMessage(role="user", content="je veux que tu eteigne cette application"),
            ChatMessage(
                role="tool",
                name="check_application_status",
                content=json.dumps(status_payload),
            ),
        ],
        tools=tools,
    )
    assert r2.tool_calls
    assert r2.tool_calls[0].name == "stop_application"
    assert r2.tool_calls[0].arguments.get("app_id") == 7
    assert r2.tool_calls[0].arguments.get("runtime") == "python"


def test_mock_start_after_status_stopped():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(
            name="check_application_status",
            description="statut",
            parameters={"type": "object", "properties": {}},
        ),
        ToolSpec(
            name="start_application",
            description="start",
            parameters={"type": "object", "properties": {}},
            dangerous=True,
        ),
    ]
    status_payload = {
        "ok": True,
        "python_apps": [
            {"id": 7, "name": "demo", "status": "stopped", "port": 8001, "domain": "x.test"}
        ],
        "node_apps": [],
    }
    r = p.chat(
        [
            ChatMessage(role="user", content="demarre mon application python"),
            ChatMessage(
                role="tool",
                name="check_application_status",
                content=json.dumps(status_payload),
            ),
        ],
        tools=tools,
    )
    assert r.tool_calls
    assert r.tool_calls[0].name == "start_application"
    assert r.tool_calls[0].arguments.get("app_id") == 7
