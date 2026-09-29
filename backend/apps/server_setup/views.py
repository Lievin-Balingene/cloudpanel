"""API configuration serveur WHM."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import VZoneAPIException
from apps.core.permissions import IsAdministrator
from apps.server_setup.ip_functions import (
    add_extra_ip,
    change_domain_ip,
    ip_usage_payload,
    remove_extra_ip,
)
from apps.server_setup.models import ServerSetup
from apps.server_setup.panel_update import (
    bootstrap_update_agent,
    enqueue_panel_update,
    get_job_status,
    panel_update_overview,
)
from apps.server_setup.repairs import (
    enqueue_repair,
    get_repair_job_status,
    repairs_overview,
)
from apps.server_setup.serializers import (
    ChangeSiteIpSerializer,
    ExtraIpSerializer,
    ServerSetupSerializer,
    TweakSettingsUpdateSerializer,
)
from apps.server_setup.services import get_setup_payload, update_setup
from apps.server_setup.tweak_settings import (
    merge_tweaks,
    tweak_payload,
    validate_tweaks,
)


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


class TweakSettingsView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        setup = ServerSetup.get_solo()
        return Response({"success": True, "data": tweak_payload(setup.tweak_settings)})

    def put(self, request: Request) -> Response:
        serializer = TweakSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cleaned = validate_tweaks(serializer.validated_data["values"])
        except ValueError as exc:
            raise VZoneAPIException(
                detail=str(exc),
                code="invalid_tweak",
                status_code=400,
            ) from exc
        setup = ServerSetup.get_solo()
        merged = merge_tweaks(setup.tweak_settings)
        merged.update(cleaned)
        setup.tweak_settings = merged
        setup.save(update_fields=["tweak_settings", "updated_at"])
        return Response({"success": True, "data": tweak_payload(setup.tweak_settings)})


class IpFunctionsView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": ip_usage_payload()})


class ExtraIpView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        serializer = ExtraIpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {"success": True, "data": add_extra_ip(serializer.validated_data["ip"])}
        )

    def delete(self, request: Request) -> Response:
        serializer = ExtraIpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {"success": True, "data": remove_extra_ip(serializer.validated_data["ip"])}
        )


class ChangeSiteIpView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        serializer = ChangeSiteIpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = change_domain_ip(
            domain_id=data["domain_id"],
            ipv4=data.get("ipv4_address"),
            actor=request.user,
        )
        return Response({"success": True, "data": result})


class PanelUpdateOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": panel_update_overview()})


class PanelUpdateBootstrapView(APIView):
    """Installe l'agent root via sudo -n (sans SSH) si sudoers le permet."""

    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        payload = bootstrap_update_agent()
        return Response({"success": True, "data": payload})


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


class RepairsOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": repairs_overview()})


class RepairStartView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        script_id = str(request.data.get("script_id") or "").strip()
        payload = enqueue_repair(
            script_id=script_id,
            requested_by=getattr(request.user, "username", "") or "",
        )
        return Response({"success": True, "data": payload}, status=202)


class RepairJobView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request, job_id: str) -> Response:
        return Response({"success": True, "data": get_repair_job_status(job_id)})


class OlsOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        from apps.domains.ols_vhosts import ols_overview

        return Response({"success": True, "data": ols_overview()})


class OlsReloadView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        from apps.domains.ols_vhosts import ols_installed, ols_ready, rebuild_ols_maps, reload_ols

        if not ols_installed():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "ols_unavailable",
                        "message": "OpenLiteSpeed non installé.",
                    },
                },
                status=400,
            )
        count = rebuild_ols_maps() if ols_ready() else 0
        reload_ols()
        return Response(
            {
                "success": True,
                "data": {"reloaded": True, "vhosts": count, "ready": ols_ready()},
            }
        )


class OlsAdoptView(APIView):
    """Passe les domaines PHP/static existants en OpenLiteSpeed."""

    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        from apps.domains.ols_vhosts import adopt_php_domains_to_ols

        payload = adopt_php_domains_to_ols()
        if not payload.get("ok"):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "ols_unavailable",
                        "message": payload.get("error") or "OLS non prêt",
                    },
                },
                status=400,
            )
        return Response({"success": True, "data": payload})
