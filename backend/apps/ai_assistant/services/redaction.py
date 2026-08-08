"""Masquage des secrets avant envoi au modèle / logs."""
from __future__ import annotations

import re
from typing import Any

SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|authorization|"
    r"access[_-]?key|refresh[_-]?token|credentials|dsn|database_url|mysql_pwd|"
    r"aws_secret|bearer)",
    re.IGNORECASE,
)

SECRET_VALUE_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|bearer)\s*[:=]\s*['\"]?[^\s'\"]+",
)

REDACTED = "***REDACTED***"


def redact_text(text: str, *, max_len: int = 12000) -> str:
    if not text:
        return ""
    out = SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    # JWT-like
    out = re.sub(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", REDACTED, out)
    if len(out) > max_len:
        out = out[:max_len] + "\n…[tronqué]"
    return out


def redact_obj(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return REDACTED
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if SECRET_KEY_RE.search(str(k)):
                out[k] = REDACTED
            else:
                out[k] = redact_obj(v, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [redact_obj(v, depth=depth + 1) for v in value[:100]]
    if isinstance(value, str):
        return redact_text(value, max_len=4000)
    return value


def strip_prompt_injection(text: str) -> str:
    """Neutralise consignes hostiles dans logs / contenus externes."""
    if not text:
        return ""
    patterns = [
        r"(?i)ignore\s+(all\s+)?previous\s+instructions",
        r"(?i)system\s*prompt",
        r"(?i)you\s+are\s+now",
        r"(?i)disregard\s+(the\s+)?above",
        r"(?i)sudo\s+rm\s+-rf",
    ]
    out = text
    for p in patterns:
        out = re.sub(p, "[filtered]", out)
    return out
