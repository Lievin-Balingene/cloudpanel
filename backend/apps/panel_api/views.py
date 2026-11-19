"""Vues jetons + points d'entrée WHM JSON API / UAPI."""
from __future__ import annotations

import json
from typing import Any

from django.db import IntegrityError
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import VZoneAPIException
from apps.panel_api.auth import TokenAuthError, authenticate_token
from apps.panel_api.dispatch import ApiCallError, call_function, public_catalog
from apps.panel_api.models import ApiToken


def _params(request) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    data: dict[str, Any] = {}
    for key, value in request.GET.items():
        data[key] = value
    if request.content_type and "json" in request.content_type and request.body:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ApiCallError("JSON invalide.") from exc
        if isinstance(body, dict):
            data.update(body)
    elif request.POST:
        for key, value in request.POST.items():
            data[key] = value
    return data


def _whm(command: str, *, result: int, reason: str, data: Any = None, status: int = 200) -> JsonResponse:
    return JsonResponse(
        {
            "metadata": {
                "version": 1,
                "reason": reason,
                "result": result,
                "command": command,
            },
            "data": data if data is not None else {},
        },
        status=status,
    )


def _uapi(module: str, func: str, *, status_ok: int, data: Any = None, errors: str | None = None, http: int = 200) -> JsonResponse:
    return JsonResponse(
        {
            "apiversion": 3,
            "module": module,
            "func": func,
            "result": {
                "status": status_ok,
                "data": data,
                "errors": [errors] if errors else None,
                "messages": None,
                "metadata": {},
                "warnings": None,
            },
        },
        status=http,
    )


@method_decorator(csrf_exempt, name="dispatch")
class WhmJsonApiView(View):
    """GET/POST /api/json-api/<fonction> — WHM API 1."""

    def get(self, request, function: str):  # type: ignore[no-untyped-def]
        return self._run(request, function)

    def post(self, request, function: str):  # type: ignore[no-untyped-def]
        return self._run(request, function)

    def _run(self, request, function: str):  # type: ignore[no-untyped-def]
        try:
            token = authenticate_token(request)
            payload = call_function(
                kind="whm",
                name=function,
                caller=token.user,
                params=_params(request),
                token=token,
            )
        except TokenAuthError as exc:
            return _whm(function, result=0, reason=exc.reason, status=exc.status)
        except ApiCallError as exc:
            return _whm(function, result=0, reason=exc.reason, status=exc.http_status)
        except VZoneAPIException as exc:
            return _whm(function, result=0, reason=str(exc.detail), status=exc.status_code)
        except Exception as exc:  # noqa: BLE001
            return _whm(function, result=0, reason=str(exc), status=500)
        return _whm(function, result=1, reason="OK", data=payload)


@method_decorator(csrf_exempt, name="dispatch")
class UapiExecuteView(View):
    """GET/POST /api/execute/<Module>/<fonction> — UAPI."""

    def get(self, request, module: str, function: str):  # type: ignore[no-untyped-def]
        return self._run(request, module, function)

    def post(self, request, module: str, function: str):  # type: ignore[no-untyped-def]
        return self._run(request, module, function)

    def _run(self, request, module: str, function: str):  # type: ignore[no-untyped-def]
        name = f"{module}.{function}"
        try:
            token = authenticate_token(request)
            payload = call_function(
                kind="uapi",
                name=name,
                caller=token.user,
                params=_params(request),
                token=token,
            )
        except TokenAuthError as exc:
            return _uapi(module, function, status_ok=0, errors=exc.reason, http=exc.status)
        except ApiCallError as exc:
            return _uapi(module, function, status_ok=0, errors=exc.reason, http=exc.http_status)
        except VZoneAPIException as exc:
            return _uapi(module, function, status_ok=0, errors=str(exc.detail), http=exc.status_code)
        except Exception as exc:  # noqa: BLE001
            return _uapi(module, function, status_ok=0, errors=str(exc), http=500)
        return _uapi(module, function, status_ok=1, data=payload)


def _token_public(token: ApiToken) -> dict:
    return {
        "id": token.id,
        "name": token.name,
        "prefix": token.token_prefix,
        "audience": token.audience,
        "scopes": token.scopes,
        "ip_allowlist": token.ip_allowlist,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
        "last_used_ip": token.last_used_ip,
        "created_at": token.created_at.isoformat() if token.created_at else None,
        "revoked": token.revoked_at is not None,
        "active": token.is_active,
    }


class ApiTokenListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):  # type: ignore[no-untyped-def]
        rows = ApiToken.objects.filter(user=request.user)
        return Response({"success": True, "data": [_token_public(t) for t in rows]})

    def post(self, request):  # type: ignore[no-untyped-def]
        if ApiToken.objects.filter(user=request.user, revoked_at__isnull=True).count() >= 25:
            return Response(
                {"success": False, "error": {"code": "limit", "message": "25 jetons actifs maximum."}},
                status=400,
            )
        name = str(request.data.get("name") or "").strip()
        if not name:
            return Response(
                {"success": False, "error": {"code": "name", "message": "Nom requis."}},
                status=400,
            )
        audience = str(request.data.get("audience") or ApiToken.Audience.UAPI)
        if audience not in ApiToken.Audience.values:
            return Response(
                {"success": False, "error": {"code": "audience", "message": "Audience invalide."}},
                status=400,
            )
        if request.user.is_client and audience != ApiToken.Audience.UAPI:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "audience",
                        "message": "Un compte client ne peut créer qu'un jeton UAPI (son propre compte).",
                    },
                },
                status=403,
            )
        scopes = request.data.get("scopes") or ["*"]
        if not isinstance(scopes, list) or not scopes:
            scopes = ["*"]
        known = {row["name"] for row in public_catalog()} | {"*"}
        bad = [s for s in scopes if s not in known]
        if bad:
            return Response(
                {"success": False, "error": {"code": "scopes", "message": f"Fonctions inconnues : {', '.join(bad)}"}},
                status=400,
            )
        days = request.data.get("expires_in_days")
        try:
            expires = int(days) if days not in (None, "", 0) else None
        except (TypeError, ValueError):
            return Response(
                {"success": False, "error": {"code": "expires", "message": "Durée invalide."}},
                status=400,
            )
        if expires is not None and not 1 <= expires <= 3650:
            return Response(
                {"success": False, "error": {"code": "expires", "message": "Durée entre 1 et 3650 jours."}},
                status=400,
            )
        try:
            token, raw = ApiToken.issue(
                user=request.user,
                name=name,
                audience=audience,
                scopes=[str(s) for s in scopes],
                ip_allowlist=str(request.data.get("ip_allowlist") or ""),
                expires_in_days=expires,
            )
        except IntegrityError:
            return Response(
                {"success": False, "error": {"code": "exists", "message": "Un jeton porte déjà ce nom."}},
                status=400,
            )
        data = _token_public(token)
        data["token"] = raw
        return Response({"success": True, "data": data}, status=201)


class ApiTokenDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk: int):  # type: ignore[no-untyped-def]
        from django.utils import timezone

        token = ApiToken.objects.filter(user=request.user, pk=pk).first()
        if token is None:
            return Response({"success": False, "error": {"code": "not_found", "message": "Jeton introuvable."}}, status=404)
        if token.revoked_at is None:
            token.revoked_at = timezone.now()
            token.save(update_fields=["revoked_at"])
        return Response({"success": True, "data": _token_public(token)})


class ApiCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):  # type: ignore[no-untyped-def]
        return Response({"success": True, "data": public_catalog()})
