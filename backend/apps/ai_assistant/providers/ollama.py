"""Provider Ollama (HTTP local ou URL BYOK client)."""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import uuid4

import requests
from django.conf import settings

from apps.ai_assistant.providers import ChatMessage, ChatResult, ToolCallRequest, ToolSpec

logger = logging.getLogger(__name__)

# Coupe-circuit serveur uniquement (pas BYOK)
_circuit_open_until: float = 0.0
_circuit_reason: str = ""


def _open_circuit(reason: str, seconds: int | None = None) -> None:
    global _circuit_open_until, _circuit_reason
    ttl = seconds if seconds is not None else int(
        getattr(settings, "VZONE_AI_OLLAMA_CIRCUIT_SEC", 600) or 600
    )
    _circuit_open_until = time.time() + max(60, ttl)
    _circuit_reason = reason[:200]
    logger.warning("Ollama circuit open %ss: %s", ttl, _circuit_reason)


def circuit_status() -> dict[str, Any]:
    open_now = time.time() < _circuit_open_until
    return {
        "open": open_now,
        "until": _circuit_open_until if open_now else 0,
        "reason": _circuit_reason if open_now else "",
    }


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        use_global_circuit: bool = True,
    ) -> None:
        self.base_url = (
            base_url
            if base_url is not None
            else (getattr(settings, "VZONE_AI_OLLAMA_URL", "http://127.0.0.1:11434") or "")
        ).rstrip("/")
        self.model = (
            model
            if model is not None
            else (getattr(settings, "VZONE_AI_OLLAMA_MODEL", "llama3.2") or "llama3.2")
        )
        default_timeout = int(getattr(settings, "VZONE_AI_TIMEOUT_SEC", 8) or 8)
        self.timeout = int(timeout if timeout is not None else default_timeout)
        self.use_global_circuit = use_global_circuit

    def is_available(self) -> bool:
        if not self.base_url:
            return False
        if self.use_global_circuit and time.time() < _circuit_open_until:
            return False
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=min(5, self.timeout))
            if r.status_code != 200:
                return False
            data = r.json() if r.content else {}
            models = data.get("models") or []
            if not models:
                return False
            names = " ".join(str(m.get("name") or "") for m in models if isinstance(m, dict))
            short = self.model.split(":")[0]
            return short in names or self.model in names
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=min(5, self.timeout))
            r.raise_for_status()
            data = r.json() if r.content else {}
            out: list[str] = []
            for m in data.get("models") or []:
                if isinstance(m, dict) and m.get("name"):
                    out.append(str(m["name"]))
            return out
        except requests.RequestException:
            return []

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        if self.use_global_circuit and time.time() < _circuit_open_until:
            raise RuntimeError(f"Ollama circuit ouvert: {_circuit_reason or 'échec récent'}")

        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": temperature},
            "messages": [_to_ollama_msg(m) for m in messages],
        }
        if tools:
            payload["tools"] = [_to_ollama_tool(t) for t in tools]
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=(5, self.timeout),
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.Timeout as exc:
            if self.use_global_circuit:
                _open_circuit(f"timeout ({self.timeout}s): {exc}")
            raise RuntimeError(f"Ollama timeout après {self.timeout}s") from exc
        except requests.RequestException as exc:
            if self.use_global_circuit:
                _open_circuit(str(exc))
            logger.warning("Ollama chat failed: %s", exc)
            raise RuntimeError(f"Ollama indisponible: {exc}") from exc

        msg = data.get("message") or {}
        content = str(msg.get("content") or "")
        tool_calls: list[ToolCallRequest] = []
        for raw in msg.get("tool_calls") or []:
            fn = raw.get("function") or raw
            name = str(fn.get("name") or "")
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            if name:
                tool_calls.append(
                    ToolCallRequest(id=str(raw.get("id") or uuid4()), name=name, arguments=args)
                )
        return ChatResult(
            content=content,
            tool_calls=tool_calls,
            raw=data if isinstance(data, dict) else {},
            provider=self.name,
            model=self.model,
        )


def _to_ollama_msg(m: ChatMessage) -> dict[str, Any]:
    out: dict[str, Any] = {"role": m.role, "content": m.content or ""}
    if m.role == "tool" and m.tool_call_id:
        out["tool_name"] = m.name
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "function": {
                    "name": tc.name,
                    "arguments": tc.arguments,
                }
            }
            for tc in m.tool_calls
        ]
    return out


def _to_ollama_tool(t: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        },
    }
