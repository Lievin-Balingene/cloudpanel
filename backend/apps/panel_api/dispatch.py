"""Catalogue et exécution des fonctions WHM / UAPI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from apps.panel_api.errors import ApiCallError
from apps.panel_api.handlers import HANDLERS


@dataclass(frozen=True)
class ApiFunction:
    name: str
    kind: str  # whm | uapi
    summary: str
    params: tuple[str, ...]
    handler: Callable[..., Any]


def _build() -> dict[str, ApiFunction]:
    catalog: dict[str, ApiFunction] = {}
    for spec in HANDLERS:
        func = ApiFunction(
            name=spec["name"],
            kind=spec["kind"],
            summary=spec["summary"],
            params=tuple(spec.get("params") or ()),
            handler=spec["handler"],
        )
        catalog[func.name] = func
    return catalog


CATALOG: dict[str, ApiFunction] = _build()


def public_catalog() -> list[dict]:
    return [
        {
            "name": fn.name,
            "kind": fn.kind,
            "summary": fn.summary,
            "params": list(fn.params),
        }
        for fn in CATALOG.values()
    ]


def call_function(*, kind: str, name: str, caller, params: dict, token) -> Any:  # type: ignore[no-untyped-def]
    func = CATALOG.get(name)
    if func is None or func.kind != kind:
        raise ApiCallError(f"Fonction inconnue: {name}", http_status=404)
    if not token.allows(kind, name):
        raise ApiCallError("Ce jeton n'a pas le droit d'appeler cette fonction.", http_status=403)
    account = _resolve_account(caller, params)
    cleaned = {
        k: v
        for k, v in params.items()
        if k
        not in {
            "cpanel_jsonapi_user",
            "cpanel_jsonapi_module",
            "cpanel_jsonapi_func",
            "cpanel_jsonapi_apiversion",
            "api.version",
            "api_token",
            "api_user",
        }
    }
    return func.handler(caller=caller, account=account, params=cleaned)


def _resolve_account(caller, params: dict):  # type: ignore[no-untyped-def]
    """WHM agit en tant que l'appelant. UAPI peut cibler un compte enfant."""
    from apps.accounts.models import User

    target = (
        params.get("cpanel_jsonapi_user")
        or params.get("account")
        or ""
    )
    target = str(target or "").strip()
    if not target or target == caller.username:
        return caller
    if caller.is_administrator:
        user = User.objects.filter(username=target).first()
    elif caller.is_reseller:
        user = User.objects.filter(username=target, parent=caller).first()
    else:
        raise ApiCallError("Un compte client ne peut agir que sur lui-même.", http_status=403)
    if user is None:
        raise ApiCallError(f"Compte introuvable: {target}", http_status=404)
    if user.is_suspended and not caller.is_administrator:
        raise ApiCallError("Compte suspendu.", http_status=403)
    return user
