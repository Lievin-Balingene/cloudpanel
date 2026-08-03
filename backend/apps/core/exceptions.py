"""Exceptions API standardisées."""
from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException, ErrorDetail
from rest_framework.response import Response
from rest_framework.views import exception_handler


class VZoneAPIException(APIException):
    """Exception de base avec code métier."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Une erreur est survenue."
    default_code = "vzone_error"

    def __init__(
        self,
        detail: str | None = None,
        code: str | None = None,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        resolved_code = code or self.default_code
        self.default_code = resolved_code
        super().__init__(detail=detail or self.default_detail, code=resolved_code)
        if status_code is not None:
            self.status_code = status_code
        self.extra = extra or {}


class QuotaExceeded(VZoneAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Quota dépassé."
    default_code = "quota_exceeded"


class ModuleDisabled(VZoneAPIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Ce module est désactivé."
    default_code = "module_disabled"


class SystemOperationError(VZoneAPIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Échec d'une opération système."
    default_code = "system_operation_error"


def vzone_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Formate toutes les erreurs API de façon uniforme."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    code: Any = getattr(exc, "default_code", None) or "error"
    if isinstance(exc, APIException):
        codes = exc.get_codes()
        if isinstance(codes, str):
            code = codes
        elif isinstance(exc.detail, ErrorDetail) and exc.detail.code:
            code = exc.detail.code

    payload: dict[str, Any] = {
        "success": False,
        "error": {
            "code": str(code),
            "message": _extract_message(response.data),
            "details": response.data,
        },
    }
    if isinstance(exc, VZoneAPIException) and exc.extra:
        payload["error"]["extra"] = exc.extra
    response.data = payload
    return response


def _extract_message(data: Any) -> str:
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        for value in data.values():
            return _extract_message(value)
    if isinstance(data, list) and data:
        return str(data[0])
    return str(data)
