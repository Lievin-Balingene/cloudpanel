"""API configuration serveur WHM."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdministrator
from apps.server_setup.panel_update import (
    enqueue_panel_update,
    get_job_status,
    panel_update_overview,
)
from apps.server_setup.serializers import ServerSetupSerializer
from apps.server_setup.services import get_setup_payload, update_setup


class ServerSetupView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": get_setup_payload()})

    def put(self, request: Request) -> Response:
        serializer = ServerSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = update_setup(
            hostname=data.get("hostname"),
            nameserver1=data.get("nameserver1"),
            nameserver2=data.get("nameserver2"),
            nameserver3=data.get("nameserver3"),
            nameserver4=data.get("nameserver4"),
            resolver1=data.get("resolver1"),
            resolver2=data.get("resolver2"),
            contact_email=data.get("contact_email"),
            apply_hostname_to_mail=data.get("apply_hostname_to_mail"),
            apply_hostname=data.get("apply_hostname", False),
        )
        return Response({"success": True, "data": payload})


class PanelUpdateOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": panel_update_overview()})


class PanelUpdateStartView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        branch = str(request.data.get("branch") or "main")
        skip_pull = bool(request.data.get("skip_pull", False))
        payload = enqueue_panel_update(
            requested_by=getattr(request.user, "username", "") or "",
            branch=branch,
            skip_pull=skip_pull,
        )
        return Response({"success": True, "data": payload}, status=202)


class PanelUpdateJobView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request, job_id: str) -> Response:
        return Response({"success": True, "data": get_job_status(job_id)})


class OlsOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        from apps.domains.ols_vhosts import ols_overview

        return Response({"success": True, "data": ols_overview()})


class OlsReloadView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        from apps.domains.ols_vhosts import ols_enabled, ols_installed, rebuild_ols_maps, reload_ols

        if not ols_enabled() or not ols_installed():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "ols_unavailable",
                        "message": "OpenLiteSpeed non installé ou désactivé.",
                    },
                },
                status=400,
            )
        count = rebuild_ols_maps()
        reload_ols()
        return Response(
            {
                "success": True,
                "data": {"reloaded": True, "vhosts": count},
            }
        )
