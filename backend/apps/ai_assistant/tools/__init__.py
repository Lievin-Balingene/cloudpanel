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


_ACCOUNT_TARGET_PROPS: dict[str, Any] = {
    "username": {
        "type": "string",
        "description": "Compte client cible (WHM/revendeur). Ignoré pour un client.",
    },
    "account": {
        "type": "string",
        "description": "Alias de username.",
    },
}

# Tools méta : pas de ciblage compte injecté dans le schéma
_NO_ACCOUNT_INJECT = frozenset(
    {
        "list_ai_capabilities",
        "list_client_accounts",
        "set_working_account",
        "clear_working_account",
        "get_server_info",
    }
)


def _with_account_props(spec: ToolSpec) -> ToolSpec:
    """Ajoute username/account optionnels pour WHM → compte client."""
    if spec.name in _NO_ACCOUNT_INJECT:
        return spec
    params = dict(spec.parameters or {})
    props = dict(params.get("properties") or {})
    if "username" in props and "account" in props:
        return spec
    props = {**_ACCOUNT_TARGET_PROPS, **props}
    params["properties"] = props
    # Conserve additionalProperties / required
    return ToolSpec(
        name=spec.name,
        description=spec.description,
        parameters=params,
        dangerous=spec.dangerous,
    )


def list_tool_specs(*, include_dangerous: bool = True) -> list[ToolSpec]:
    specs = []
    for item in _REGISTRY.values():
        if item.dangerous and not include_dangerous:
            continue
        specs.append(_with_account_props(item.spec))
    return specs


def ensure_tools_loaded() -> None:
    # Import side-effects — enregistre tous les handlers whitelistés
    from apps.ai_assistant.tools import (  # noqa: F401
        handlers,
        handlers_account,
        handlers_apps_extra,
        handlers_backups,
        handlers_client_extra,
        handlers_cron,
        handlers_databases,
        handlers_dns,
        handlers_docker,
        handlers_domains,
        handlers_email,
        handlers_files,
        handlers_ftp,
        handlers_git_extra,
        handlers_k8s,
        handlers_php,
        handlers_wordpress,
    )

    return None
