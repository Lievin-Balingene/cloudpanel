"""Provider compatible OpenAI (vLLM, LM Studio, OpenRouter, clé client BYOK)."""
from __future__ import annotations

import json
import logging
import re
import time
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

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


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
        self.max_retries = int(getattr(settings, "VZONE_AI_BYOK_HTTP_RETRIES", 3) or 3)

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
        model_switched = False
        attempts = max(2, self.max_retries + 1)

        for attempt in range(attempts):
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
            except requests.Timeout as exc:
                last_err = f"Timeout après {self.timeout}s"
                if attempt < attempts - 1:
                    time.sleep(min(2**attempt, 8))
                    continue
                raise RuntimeError(f"Provider OpenAI-compat indisponible: {last_err}") from exc
            except requests.RequestException as exc:
                logger.warning("OpenAI-compat chat failed: %s", exc)
                raise RuntimeError(f"Provider OpenAI-compat indisponible: {exc}") from exc

            if resp.status_code < 400:
                data = resp.json()
                self.model = model
                return _parse_openai_result(data, self.name, model)

            body = (resp.text or "")[:600]
            last_err = _friendly_http_error(resp.status_code, self.base_url, body)

            # 404 modèle retiré → bascule une fois vers le modèle suggéré
            suggested = _extract_suggested_model(body)
            if (
                not model_switched
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
                model_switched = True
                continue

            # Surcharge / rate-limit → backoff
            if resp.status_code in _RETRYABLE_STATUS and attempt < attempts - 1:
                delay = min(2**attempt, 8)
                logger.warning(
                    "OpenAI-compat HTTP %s (tentative %s/%s) — attente %ss",
                    resp.status_code,
                    attempt + 1,
                    attempts,
                    delay,
                )
                time.sleep(delay)
                continue
            break

        raise RuntimeError(last_err)


def _friendly_http_error(status: int, base_url: str, body: str) -> str:
    low = (body or "").lower()
    if status == 503 or "high demand" in low or "unavailable" in low:
        return (
            f"HTTP {status} — Gemini / le provider est temporairement saturé "
            "(forte demande). Réessayez dans quelques secondes, ou passez à "
            "`gemini-3.5-flash-lite` / `gemini-3.7-flash` dans ⚙ Mon modèle IA."
        )
    if status == 429 or "rate" in low and "limit" in low:
        return (
            f"HTTP {status} — quota / rate-limit atteint. Attendez un moment "
            "ou vérifiez les limites de votre clé API."
        )
    if status == 400 and "thought_signature" in low:
        return (
            "HTTP 400 — Gemini exige le round-trip des thought_signature sur les outils. "
            "Mettez à jour le panel (0.39.6+) puis réessayez. "
            f"Détail: {body[:280]}"
        )
    return f"HTTP {status} sur {base_url}/chat/completions — {body}"


def _extract_suggested_model(body: str) -> str:
    m = _MODEL_MIGRATE_RE.search(body or "")
    if not m:
        return ""
    return m.group(1).strip()


def _parse_openai_result(data: dict[str, Any], provider: str, model: str) -> ChatResult:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = str(msg.get("content") or "")
    msg_sig = _extract_thought_signature(msg)
    tool_calls: list[ToolCallRequest] = []
    for raw in msg.get("tool_calls") or []:
        if not isinstance(raw, dict):
            continue
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
                    thought_signature=_extract_thought_signature(raw),
                )
            )
    # Si signature uniquement au niveau message et 1er tool sans sig → propager
    if msg_sig and tool_calls and not tool_calls[0].thought_signature:
        tool_calls[0].thought_signature = msg_sig
    return ChatResult(
        content=content,
        tool_calls=tool_calls,
        raw=data if isinstance(data, dict) else {},
        provider=provider,
        model=model,
    )


def _extract_thought_signature(obj: dict[str, Any] | None) -> str:
    if not isinstance(obj, dict):
        return ""
    # Formats documentés / observés
    for key in ("thought_signature", "thoughtSignature"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    extra = obj.get("extra_content") or obj.get("extraContent") or {}
    if isinstance(extra, dict):
        google = extra.get("google") or {}
        if isinstance(google, dict):
            for key in ("thought_signature", "thoughtSignature"):
                val = google.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    return ""


def _to_openai_msg(m: ChatMessage) -> dict[str, Any]:
    if m.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": m.tool_call_id or "tool",
            "content": m.content or "",
        }
    # Gemini docs utilisent parfois role=model ; l'endpoint OpenAI attend assistant
    role = "assistant" if m.role in {"assistant", "model"} else m.role
    out: dict[str, Any] = {"role": role, "content": m.content or ""}
    if m.tool_calls:
        serialized = []
        for idx, tc in enumerate(m.tool_calls):
            item: dict[str, Any] = {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            sig = (tc.thought_signature or "").strip()
            # Gemini 3 : 1er functionCall du step DOIT avoir une signature.
            # Si absente (historique / provider incomplet) → bypass documenté.
            if not sig and idx == 0:
                sig = "skip_thought_signature_validator"
            if sig:
                item["extra_content"] = {"google": {"thought_signature": sig}}
            serialized.append(item)
        out["tool_calls"] = serialized
    elif m.thought_signature:
        out["extra_content"] = {"google": {"thought_signature": m.thought_signature}}
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
