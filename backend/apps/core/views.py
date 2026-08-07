"""Vues API du module core."""
from __future__ import annotations

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.module_registry import registry
from apps.core.permissions import IsAdministrator
from apps.core.serializers import HealthSerializer, ModuleSerializer, VersionSerializer
from apps.core.services import collect_system_metrics, health_as_dict
from apps.packages.models import PackageAssignment
from vzone import __version__


class HealthCheckView(APIView):
    """Endpoint public de santé (liveness / readiness)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses=HealthSerializer)
    def get(self, request: Request) -> Response:
        payload = health_as_dict()
        status_code = 200 if payload["status"] == "healthy" else 503
        return Response({"success": True, "data": payload}, status=status_code)


class VersionView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses=VersionSerializer)
    def get(self, request: Request) -> Response:
        return Response(
            {
                "success": True,
                "data": {
                    "version": __version__,
                    "product": "V-zone Panel",
                    "api": "v1",
                },
            }
        )


class ModuleListView(APIView):
    """Liste des modules enregistrés (admins uniquement)."""

    permission_classes = [IsAuthenticated, IsAdministrator]

    @extend_schema(responses=ModuleSerializer(many=True))
    def get(self, request: Request) -> Response:
        modules = [
            {
                "name": m.name,
                "label": m.label,
                "version": m.version,
                "description": m.description,
                "enabled": registry.is_enabled(m.name),
                "dependencies": list(m.dependencies),
            }
            for m in registry.all()
        ]
        return Response({"success": True, "data": modules})


class SystemMetricsView(APIView):
    """Métriques système instantanées (CPU, RAM, disque…)."""

    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": collect_system_metrics()})


class WebTerminalAccessView(APIView):
    """Retourne l'accès terminal (admin=root WHM, client=jail si package allow_ssh)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        allowed = False
        reason = "SSH désactivé dans votre package."
        mode = "jail"
        role = getattr(user, "role", None)
        if role == "administrator":
            allowed = bool(getattr(settings, "VZONE_TERMINAL_ALLOW_ADMIN", True))
            mode = "root"
            reason = "Terminal WHM root (administrateur)." if allowed else "Terminal admin désactivé."
        elif role == "reseller":
            allowed = True
            mode = "jail"
            reason = "Terminal revendeur (jailé)."
        else:
            assignment = (
                PackageAssignment.objects.filter(user=user).select_related("package").first()
            )
            if assignment and assignment.package and assignment.package.allow_ssh:
                allowed = True
                reason = "Autorisé par le package."
        jail = (
            getattr(user, "system_username", None) or getattr(user, "username", "") or ""
        ).strip().lower()
        if mode == "root":
            home = "/root"
            display_user = "root"
        else:
            home = getattr(user, "home_directory", "") or ""
            if not home and jail:
                root = getattr(settings, "VZONE_HOME_ROOT", "/home")
                home = f"{root}/{jail}"
            display_user = jail or user.username
        return Response(
            {
                "success": True,
                "data": {
                    "allowed": allowed,
                    "reason": reason,
                    "mode": mode,
                    "home_directory": home,
                    "username": display_user,
                    "prompt_user": display_user,
                },
            }
        )
