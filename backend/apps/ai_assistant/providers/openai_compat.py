"""Provider compatible OpenAI (vLLM, LM Studio, OpenRouter, clé client BYOK)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import uuid4

import requests
from django.conf import settings

from apps.ai_assistant.providers import ChatMessage, ChatResult, ToolCallRequest, ToolSpec

logger = logging.getLogger(__name__)

# Google : « Please update your code to use models/gemini-3.5-flash »
_MODEL_MIGRATE_RE = re.compile(
    r"(?:update your code to use|use)\s+models/([a-zA-Z0-9._-]+)",
    re.IGNORECASE,
)


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (
            base_url
            if base_url is not None
            else (getattr(settings, "VZONE_AI_OPENAI_BASE_URL", "") or "")
        ).rstrip("/")
        self.api_key = (
            api_key
            if api_key is not None
            else (getattr(settings, "VZONE_AI_OPENAI_API_KEY", "") or "")
        )
        self.model = (
            model
            if model is not None
            else (getattr(settings, "VZONE_AI_OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini")
        )
        default_timeout = int(getattr(settings, "VZONE_AI_TIMEOUT_SEC", 90) or 90)
        self.timeout = int(timeout if timeout is not None else default_timeout)

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

        model = self.model
        last_err = ""
        for attempt in range(2):
            payload: dict[str, Any] = {
                "model": model,
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
            except requests.RequestException as exc:
                logger.warning("OpenAI-compat chat failed: %s", exc)
                raise RuntimeError(f"Provider OpenAI-compat indisponible: {exc}") from exc

            if resp.status_code < 400:
                data = resp.json()
                self.model = model  # mémorise le modèle effectivement utilisé
                return _parse_openai_result(data, self.name, model)

            body = (resp.text or "")[:600]
            last_err = f"HTTP {resp.status_code} sur {self.base_url}/chat/completions — {body}"
            suggested = _extract_suggested_model(body)
            if (
                attempt == 0
                and resp.status_code == 404
                and suggested
                and suggested.lower() != model.lower()
            ):
                logger.warning(
                    "Modèle %s indisponible — retry avec %s (suggestion provider)",
                    model,
                    suggested,
                )
                model = suggested
                continue
            break

        raise RuntimeError(last_err)


def _extract_suggested_model(body: str) -> str:
    m = _MODEL_MIGRATE_RE.search(body or "")
    if not m:
        return ""
    return m.group(1).strip()


def _parse_openai_result(data: dict[str, Any], provider: str, model: str) -> ChatResult:
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
        provider=provider,
        model=model,
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
