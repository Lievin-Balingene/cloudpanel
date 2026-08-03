"""Middleware : forcer le changement de mot de passe (JWT / session)."""
from __future__ import annotations

from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


ALLOWED_WHEN_MUST_CHANGE = (
    "/api/v1/auth/password/",
    "/api/v1/auth/logout/",
    "/api/v1/auth/me/",
    "/api/v1/auth/refresh/",
    "/api/v1/auth/2fa/",
    "/api/v1/security/me/",
    "/api/v1/health/",
    "/api/v1/version/",
)


class ForcePasswordChangeMiddleware(MiddlewareMixin):
    """Bloque l'API si must_change_password, sauf endpoints auth essentiels."""

    def process_view(self, request, view_func, view_args, view_kwargs):  # type: ignore[no-untyped-def]
        if not request.path.startswith("/api/"):
            return None
        user = self._resolve_user(request)
        if not user or not getattr(user, "must_change_password", False):
            return None
        path = request.path
        if any(path.startswith(p) for p in ALLOWED_WHEN_MUST_CHANGE):
            return None
        return JsonResponse(
            {
                "success": False,
                "error": {
                    "code": "must_change_password",
                    "message": "Vous devez changer votre mot de passe avant de continuer.",
                },
            },
            status=403,
        )

    def _resolve_user(self, request):  # type: ignore[no-untyped-def]
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user
        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication

            result = JWTAuthentication().authenticate(request)
            if result:
                return result[0]
        except Exception:
            return None
        return None
