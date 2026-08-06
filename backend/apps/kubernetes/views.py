from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdministrator
from apps.kubernetes.serializers import KubernetesManifestSerializer
from apps.kubernetes.services import apply_manifest, delete_manifest, list_resources, overview_for


class KubernetesOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for()})


class KubernetesResourcesView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": list_resources(soft=True)})


class KubernetesApplyView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        serializer = KubernetesManifestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            {
                "success": True,
                "data": apply_manifest(data["manifest"], data.get("namespace", "")),
            }
        )


class KubernetesDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        serializer = KubernetesManifestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            {
                "success": True,
                "data": delete_manifest(data["manifest"], data.get("namespace", "")),
            }
        )
