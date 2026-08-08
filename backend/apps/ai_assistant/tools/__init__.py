"""Registre whitelist des outils agent (pas de shell arbitraire)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from apps.ai_assistant.providers import ToolSpec

ToolHandler = Callable[[Any, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class RegisteredTool:
    spec: ToolSpec
    handler: ToolHandler
    # write = nécessite confirmation utilisateur
    dangerous: bool = False


_REGISTRY: dict[str, RegisteredTool] = {}


def register_tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    dangerous: bool = False,
) -> Callable[[ToolHandler], ToolHandler]:
    def decorator(fn: ToolHandler) -> ToolHandler:
        _REGISTRY[name] = RegisteredTool(
            spec=ToolSpec(
                name=name,
                description=description,
                parameters=parameters,
                dangerous=dangerous,
            ),
            handler=fn,
            dangerous=dangerous,
        )
        return fn

    return decorator


def get_tool(name: str) -> RegisteredTool | None:
    return _REGISTRY.get(name)


def list_tool_specs(*, include_dangerous: bool = True) -> list[ToolSpec]:
    specs = []
    for item in _REGISTRY.values():
        if item.dangerous and not include_dangerous:
            continue
        specs.append(item.spec)
    return specs


def ensure_tools_loaded() -> None:
    # Import side-effects
    from apps.ai_assistant.tools import handlers  # noqa: F401

    return None
