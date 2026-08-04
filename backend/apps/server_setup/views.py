"""API configuration serveur WHM."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdministrator
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
            apply_hostname=data.get("apply_hostname", True),
        )
        return Response({"success": True, "data": payload})
