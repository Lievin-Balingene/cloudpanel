"""Provider compatible OpenAI (vLLM, LM Studio, OpenRouter gratuit, etc.)."""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

import requests
from django.conf import settings

from apps.ai_assistant.providers import ChatMessage, ChatResult, ToolCallRequest, ToolSpec

logger = logging.getLogger(__name__)


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self) -> None:
        self.base_url = (
            getattr(settings, "VZONE_AI_OPENAI_BASE_URL", "") or ""
        ).rstrip("/")
        self.api_key = getattr(settings, "VZONE_AI_OPENAI_API_KEY", "") or ""
        self.model = getattr(settings, "VZONE_AI_OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        self.timeout = int(getattr(settings, "VZONE_AI_TIMEOUT_SEC", 90) or 90)

    def is_available(self) -> bool:
        return bool(self.base_url)

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        if not self.base_url:
            raise RuntimeError("VZONE_AI_OPENAI_BASE_URL non configuré")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": [_to_openai_msg(m) for m in messages],
        }
        if tools:
            payload["tools"] = [_to_openai_tool(t) for t in tools]
            payload["tool_choice"] = "auto"
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.warning("OpenAI-compat chat failed: %s", exc)
            raise RuntimeError(f"Provider OpenAI-compat indisponible: {exc}") from exc

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = str(msg.get("content") or "")
        tool_calls: list[ToolCallRequest] = []
        for raw in msg.get("tool_calls") or []:
            fn = raw.get("function") or {}
            name = str(fn.get("name") or "")
            args_raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            if name:
                tool_calls.append(
                    ToolCallRequest(
                        id=str(raw.get("id") or uuid4()),
                        name=name,
                        arguments=args,
                    )
                )
        return ChatResult(
            content=content,
            tool_calls=tool_calls,
            raw=data if isinstance(data, dict) else {},
            provider=self.name,
            model=self.model,
        )


def _to_openai_msg(m: ChatMessage) -> dict[str, Any]:
    if m.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": m.tool_call_id or "tool",
            "content": m.content or "",
        }
    out: dict[str, Any] = {"role": m.role, "content": m.content or ""}
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in m.tool_calls
        ]
    return out


def _to_openai_tool(t: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        },
    }
