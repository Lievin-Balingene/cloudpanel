"""Middleware transverses : corrélation des requêtes et audit léger."""
from __future__ import annotations

import logging
import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("apps.core.audit")


class RequestIDMiddleware(MiddlewareMixin):
    """Attache un X-Request-ID à chaque requête/réponse."""

    HEADER = "X-Request-ID"

    def process_request(self, request: HttpRequest) -> None:
        request_id = request.headers.get(self.HEADER) or str(uuid.uuid4())
        request.request_id = request_id  # type: ignore[attr-defined]

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        request_id = getattr(request, "request_id", None)
        if request_id:
            response[self.HEADER] = request_id
        return response


class AuditMiddleware:
    """Journalise les mutations authentifiées (POST/PUT/PATCH/DELETE)."""

    MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if request.method in self.MUTATING and getattr(request, "user", None):
            user = request.user
            if user.is_authenticated:
                logger.info(
                    "audit method=%s path=%s status=%s user=%s request_id=%s",
                    request.method,
                    request.path,
                    response.status_code,
                    user.pk,
                    getattr(request, "request_id", "-"),
                )
        return response
