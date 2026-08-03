"""Vues API du module core."""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.module_registry import registry
from apps.core.permissions import IsAdministrator
from apps.core.serializers import HealthSerializer, ModuleSerializer, VersionSerializer
from apps.core.services import collect_system_metrics, health_as_dict
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
