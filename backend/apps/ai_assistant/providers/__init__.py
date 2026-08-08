"""Abstraction fournisseurs LLM — interchangeable sans toucher l'agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatMessage:
    role: str  # system|user|assistant|tool
    content: str = ""
    name: str = ""
    tool_call_id: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    model: str = ""


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object
    dangerous: bool = False


class LLMProvider(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
    ) -> ChatResult: ...


def get_provider(name: str | None = None) -> LLMProvider:
    from django.conf import settings

    from apps.ai_assistant.providers.mock import MockProvider
    from apps.ai_assistant.providers.ollama import OllamaProvider
    from apps.ai_assistant.providers.openai_compat import OpenAICompatProvider

    chosen = (name or getattr(settings, "VZONE_AI_PROVIDER", "auto") or "auto").lower()
    ollama = OllamaProvider()
    openai = OpenAICompatProvider()
    mock = MockProvider()

    if chosen == "ollama":
        return ollama
    if chosen in {"openai", "openai_compat", "vllm", "lmstudio"}:
        return openai
    if chosen == "mock":
        return mock
    # auto : Ollama → OpenAI-compat → mock
    if ollama.is_available():
        return ollama
    if openai.is_available():
        return openai
    return mock
