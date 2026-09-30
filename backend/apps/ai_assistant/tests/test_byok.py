"""Tests BYOK — provider client (Ollama / OpenAI-compat)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.ai_assistant.models import UserAiProviderSettings
from apps.ai_assistant.services.provider_resolve import (
    get_provider_for_user,
    provider_source_for_user,
    reset_user_provider_settings,
    update_user_provider_settings,
)
from apps.ai_assistant.services.url_safety import validate_byok_url
from apps.core.exceptions import VZoneAPIException
from apps.databases.crypto import decrypt_secret


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def test_validate_byok_url_rejects_localhost(settings):
    settings.VZONE_AI_BYOK_ALLOW_PRIVATE_URLS = False
    with pytest.raises(VZoneAPIException) as exc:
        validate_byok_url("http://127.0.0.1:11434")
    assert exc.value.default_code == "byok_url_private" or "privé" in str(exc.value.detail).lower() or "SSRF" in str(
        exc.value.detail
    )


def test_validate_byok_url_allows_private_when_opt_in(settings):
    settings.VZONE_AI_BYOK_ALLOW_PRIVATE_URLS = True
    url = validate_byok_url("http://127.0.0.1:11434")
    assert url.startswith("http://127.0.0.1:11434")


def test_validate_byok_url_rejects_credentials():
    with pytest.raises(VZoneAPIException):
        validate_byok_url("https://user:pass@api.openai.com/v1")


def test_validate_byok_url_https_public(settings):
    settings.VZONE_AI_BYOK_ALLOW_PRIVATE_URLS = False
    # example.com is public — may resolve; if DNS fails in sandbox, skip soft
    try:
        url = validate_byok_url("https://example.com/v1")
        assert url.startswith("https://example.com")
    except VZoneAPIException as exc:
        if getattr(exc, "default_code", "") == "byok_url_dns":
            pytest.skip("DNS indisponible dans l'environnement de test")
        raise


def test_normalize_gemini_model_aliases():
    from apps.ai_assistant.services.provider_resolve import normalize_gemini_model

    assert normalize_gemini_model("gemini-1.5-flash") == "gemini-3.5-flash"
    assert normalize_gemini_model("models/gemini-2.0-flash") == "gemini-3.5-flash"
    assert normalize_gemini_model("gemini-2.5-flash") == "gemini-3.5-flash"
    assert normalize_gemini_model("gemini-3.5-flash") == "gemini-3.5-flash"
    assert normalize_gemini_model("") == "gemini-3.5-flash"


def test_openai_compat_retries_suggested_gemini_model(settings):
    from unittest.mock import MagicMock, patch

    from apps.ai_assistant.providers import ChatMessage
    from apps.ai_assistant.providers.openai_compat import OpenAICompatProvider

    p = OpenAICompatProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="test-key",
        model="gemini-2.5-flash",
        timeout=5,
    )
    fail = MagicMock()
    fail.status_code = 404
    fail.text = (
        '{"error":{"message":"This model models/gemini-2.5-flash is no longer available '
        'to new users. Please update your code to use models/gemini-3.5-flash for the latest"}}'
    )
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {
        "choices": [{"message": {"content": "bonjour", "tool_calls": []}}],
    }
    with patch("apps.ai_assistant.providers.openai_compat.requests.post", side_effect=[fail, ok]) as mock_post:
        result = p.chat([ChatMessage(role="user", content="hi")])
    assert result.content == "bonjour"
    assert result.model == "gemini-3.5-flash"
    assert mock_post.call_count == 2
    assert mock_post.call_args_list[1].kwargs["json"]["model"] == "gemini-3.5-flash"


def test_openai_compat_retries_on_503(settings):
    from unittest.mock import MagicMock, patch

    from apps.ai_assistant.providers import ChatMessage
    from apps.ai_assistant.providers.openai_compat import OpenAICompatProvider

    p = OpenAICompatProvider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="test-key",
        model="gemini-3.5-flash",
        timeout=5,
    )
    p.max_retries = 2
    busy = MagicMock()
    busy.status_code = 503
    busy.text = '{"error":{"message":"high demand","status":"UNAVAILABLE"}}'
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {
        "choices": [{"message": {"content": "ok apres retry", "tool_calls": []}}],
    }
    with (
        patch("apps.ai_assistant.providers.openai_compat.requests.post", side_effect=[busy, ok]),
        patch("apps.ai_assistant.providers.openai_compat.time.sleep") as sleep,
    ):
        result = p.chat([ChatMessage(role="user", content="hi")])
    assert result.content == "ok apres retry"
    assert sleep.called


def test_normalize_openai_compat_gemini_url():
    from apps.ai_assistant.services.provider_resolve import normalize_openai_compat_base_url

    gemini = "https://generativelanguage.googleapis.com/v1beta/openai"
    assert normalize_openai_compat_base_url(gemini) == gemini
    assert normalize_openai_compat_base_url(gemini + "/") == gemini
    # Racine Google → ajoute /openai (pas /v1)
    root = "https://generativelanguage.googleapis.com/v1beta"
    assert normalize_openai_compat_base_url(root) == f"{root}/openai"
    assert normalize_openai_compat_base_url("https://api.openai.com") == "https://api.openai.com/v1"
    assert normalize_openai_compat_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


@pytest.mark.django_db
def test_update_and_resolve_byok_ollama(settings):
    settings.VZONE_AI_BYOK_ENABLED = True
    settings.VZONE_AI_BYOK_ALLOW_PRIVATE_URLS = True
    settings.VZONE_AI_PROVIDER = "mock"
    user = UserFactory(username="byokollama", password="TestPassword123!")

    obj = update_user_provider_settings(
        user,
        mode="ollama",
        base_url="http://127.0.0.1:11434",
        model_name="llama3.2:1b",
    )
    assert obj.is_byok_active
    assert provider_source_for_user(user) == "byok"

    with patch("apps.ai_assistant.providers.ollama.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"models":[{"name":"llama3.2:1b"}]}'
        mock_resp.json.return_value = {"models": [{"name": "llama3.2:1b"}]}
        mock_get.return_value = mock_resp
        provider = get_provider_for_user(user)
        assert provider.name == "ollama"
        assert provider.model == "llama3.2:1b"
        assert provider.is_available() is True

    reset_user_provider_settings(user)
    assert provider_source_for_user(user) == "server"
    assert get_provider_for_user(user).name == "mock"


@pytest.mark.django_db
def test_byok_openai_key_encrypted(settings):
    settings.VZONE_AI_BYOK_ENABLED = True
    settings.VZONE_AI_BYOK_ALLOW_PRIVATE_URLS = True
    user = UserFactory(username="byokopenai", password="TestPassword123!")
    obj = update_user_provider_settings(
        user,
        mode="openai_compat",
        base_url="http://127.0.0.1:1234/v1",
        model_name="gpt-test",
        api_key="sk-secret-test-key",
    )
    obj.refresh_from_db()
    assert obj.api_key_encrypted
    assert "sk-secret" not in obj.api_key_encrypted
    assert decrypt_secret(obj.api_key_encrypted) == "sk-secret-test-key"

    provider = get_provider_for_user(user)
    assert provider.name == "openai_compat"
    assert provider.api_key == "sk-secret-test-key"
    assert provider.model == "gpt-test"


@pytest.mark.django_db
def test_byok_api_endpoints(api: APIClient, settings):
    settings.VZONE_AI_BYOK_ENABLED = True
    settings.VZONE_AI_BYOK_ALLOW_PRIVATE_URLS = True
    settings.VZONE_AI_PROVIDER = "mock"
    user = UserFactory(username="byokapi", password="TestPassword123!")
    api.force_authenticate(user=user)

    status = api.get(reverse("ai-status"))
    assert status.status_code == 200
    body = status.json()["data"]
    assert body["byok_enabled"] is True
    assert body["provider_source"] == "server"
    assert "byok" in body

    put = api.put(
        reverse("ai-provider-settings"),
        {
            "mode": "ollama",
            "base_url": "http://10.0.0.5:11434",
            "model_name": "mistral",
        },
        format="json",
    )
    assert put.status_code == 200, put.content
    assert put.json()["data"]["settings"]["mode"] == "ollama"
    assert put.json()["data"]["provider_source"] == "byok"
    assert put.json()["data"]["settings"]["has_api_key"] is False

    get = api.get(reverse("ai-provider-settings"))
    assert get.status_code == 200
    assert get.json()["data"]["settings"]["model_name"] == "mistral"

    with patch(
        "apps.ai_assistant.services.provider_resolve.build_byok_provider"
    ) as mock_build:
        mock_p = MagicMock()
        mock_p.name = "ollama"
        mock_p.model = "mistral"
        mock_p.is_available.return_value = True
        mock_p.list_models.return_value = ["mistral"]
        mock_build.return_value = mock_p
        tested = api.post(
            reverse("ai-provider-test"),
            {"mode": "ollama", "base_url": "http://10.0.0.5:11434", "model_name": "mistral"},
            format="json",
        )
    assert tested.status_code == 200
    assert tested.json()["data"]["ok"] is True

    deleted = api.delete(reverse("ai-provider-settings"))
    assert deleted.status_code == 200
    assert deleted.json()["data"]["provider_source"] == "server"
    assert UserAiProviderSettings.objects.get(owner=user).mode == "server"


@pytest.mark.django_db
def test_byok_disabled_blocks_put(api: APIClient, settings):
    settings.VZONE_AI_BYOK_ENABLED = False
    user = UserFactory(username="byokoff", password="TestPassword123!")
    api.force_authenticate(user=user)
    put = api.put(
        reverse("ai-provider-settings"),
        {"mode": "ollama", "base_url": "https://example.com", "model_name": "x"},
        format="json",
    )
    assert put.status_code == 403


@pytest.mark.django_db
def test_conversation_uses_byok_provider(api: APIClient, settings):
    settings.VZONE_AI_BYOK_ENABLED = True
    settings.VZONE_AI_BYOK_ALLOW_PRIVATE_URLS = True
    settings.VZONE_AI_PROVIDER = "mock"
    user = UserFactory(username="byokchat", password="TestPassword123!")
    update_user_provider_settings(
        user,
        mode="ollama",
        base_url="http://127.0.0.1:11434",
        model_name="llama3.2",
    )
    api.force_authenticate(user=user)
    created = api.post(reverse("ai-conversation-list"), {}, format="json")
    pk = created.json()["data"]["id"]

    with patch("apps.ai_assistant.services.agent.get_provider_for_user") as mock_gp:
        from apps.ai_assistant.providers.mock import MockProvider

        mock_gp.return_value = MockProvider()
        msg = api.post(
            reverse("ai-conversation-message", kwargs={"pk": pk}),
            {"message": "bonjour"},
            format="json",
        )
    assert msg.status_code == 200
    assert msg.json()["data"]["provider"] == "mock"
    # source still byok even if we mocked the provider instance
    assert msg.json()["data"].get("provider_source") == "byok"
