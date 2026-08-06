"""Middleware : isolation portail Admin/Client après authentification."""
from __future__ import annotations

from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from apps.security.portal import assert_role_allowed_on_portal, request_portal


# Login reste exempt (contrôle dans LoginSerializer). Refresh est contrôlé dans RefreshTokenView.
AUTH_EXEMPT_PREFIXES = (
    "/api/v1/auth/login/",
    "/api/v1/health/",
    "/api/v1/version/",
    "/api/v1/ftp/auth/",
    "/api/v1/ftp/logs/ingest/",
    "/api/v1/git/webhook/",
)


class PortalIsolationMiddleware(MiddlewareMixin):
    """
    Applique X-Vzone-Portal (posé par nginx) à toutes les requêtes API authentifiées.
    Port Admin → pas de JWT client ; port Client → pas de JWT admin/revendeur.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):  # type: ignore[no-untyped-def]
        if not request.path.startswith("/api/"):
            return None
        if any(request.path.startswith(p) for p in AUTH_EXEMPT_PREFIXES):
            return None

        portal = request_portal(request)
        if portal not in {"admin", "client", "webmail"}:
            return None

        # Refresh : géré dans RefreshTokenView (body refresh, pas toujours Authorization)
        if request.path.startswith("/api/v1/auth/refresh/"):
            return None

        user = self._resolve_user(request)
        if user is None:
            return None

        try:
            assert_role_allowed_on_portal(user, portal)
        except Exception as exc:  # noqa: BLE001
            from apps.core.exceptions import VZoneAPIException

            if isinstance(exc, VZoneAPIException):
                return JsonResponse(
                    {
                        "success": False,
                        "error": {
                            "code": getattr(exc, "default_code", None) or "wrong_portal",
                            "message": str(exc.detail),
                        },
                    },
                    status=int(getattr(exc, "status_code", 403) or 403),
                )
            raise
        return None

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
