"""API applications Node.js."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.node_apps.serializers import (
    NodeAppCreateSerializer,
    NodeAppSerializer,
    NodeAppUpdateSerializer,
)
from apps.node_apps.services import (
    apps_qs,
    create_node_app,
    delete_node_app,
    npm_install,
    overview_for,
    read_logs,
    restart_node_app,
    start_node_app,
    stop_node_app,
    update_node_app,
)


def _resolve_owner(request: Request, owner_id: int | None) -> User:
    owner = request.user
    if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
        owner = get_object_or_404(User, pk=owner_id)
        if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
            raise PermissionError
    return owner


class NodeOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class NodeAppListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = apps_qs(request.user)
        return Response({"success": True, "data": NodeAppSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = NodeAppCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        app = create_node_app(
            owner=owner,
            name=data["name"],
            label=data.get("label", ""),
            node_version=data.get("node_version", "20"),
            framework=data.get("framework", "generic"),
            relative_root=data.get("relative_root", ""),
            start_script=data.get("start_script", "start"),
            entrypoint=data.get("entrypoint", "server.js"),
            domain_name=data.get("domain_name", ""),
            env_vars=data.get("env_vars") or {},
            notes=data.get("notes", ""),
        )
        return Response(
            {"success": True, "data": NodeAppSerializer(app).data},
            status=status.HTTP_201_CREATED,
        )


class NodeAppDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        return Response({"success": True, "data": NodeAppSerializer(app).data})

    def patch(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        serializer = NodeAppUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        app = update_node_app(app, **serializer.validated_data)
        return Response({"success": True, "data": NodeAppSerializer(app).data})

    def delete(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        remove_files = str(request.query_params.get("remove_files", "false")).lower() in {
            "1",
            "true",
            "yes",
        }
        delete_node_app(app, remove_files=remove_files)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NodeAppStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        app = start_node_app(app)
        return Response({"success": True, "data": NodeAppSerializer(app).data})


class NodeAppStopView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        app = stop_node_app(app)
        return Response({"success": True, "data": NodeAppSerializer(app).data})


class NodeAppRestartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        app = restart_node_app(app)
        return Response({"success": True, "data": NodeAppSerializer(app).data})


class NodeAppInstallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        result = npm_install(app)
        return Response({"success": True, "data": result})


class NodeAppLogsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        lines = int(request.query_params.get("lines", 100))
        return Response({"success": True, "data": read_logs(app, lines=min(lines, 1000))})
