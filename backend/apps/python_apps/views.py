"""API applications Python."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.python_apps.serializers import (
    PythonAppCreateSerializer,
    PythonAppSerializer,
    PythonAppUpdateSerializer,
)
from apps.python_apps.services import (
    apps_qs,
    create_python_app,
    delete_python_app,
    install_requirements,
    overview_for,
    read_logs,
    restart_python_app,
    start_python_app,
    stop_python_app,
    update_python_app,
)


def _resolve_owner(request: Request, owner_id: int | None) -> User:
    owner = request.user
    if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
        owner = get_object_or_404(User, pk=owner_id)
        if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
            raise PermissionError
    return owner


class PythonOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class PythonAppListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = apps_qs(request.user)
        return Response({"success": True, "data": PythonAppSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = PythonAppCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        app = create_python_app(
            owner=owner,
            name=data["name"],
            label=data.get("label", ""),
            python_version=data.get("python_version", "3.12"),
            mode=data.get("mode", "wsgi"),
            framework=data.get("framework", "generic"),
            relative_root=data.get("relative_root", ""),
            entrypoint=data.get("entrypoint", ""),
            domain_name=data.get("domain_name", ""),
            env_vars=data.get("env_vars") or {},
            notes=data.get("notes", ""),
        )
        return Response(
            {"success": True, "data": PythonAppSerializer(app).data},
            status=status.HTTP_201_CREATED,
        )


class PythonAppDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        return Response({"success": True, "data": PythonAppSerializer(app).data})

    def patch(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        serializer = PythonAppUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        app = update_python_app(app, **serializer.validated_data)
        return Response({"success": True, "data": PythonAppSerializer(app).data})

    def delete(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        remove_files = str(request.query_params.get("remove_files", "false")).lower() in {
            "1",
            "true",
            "yes",
        }
        delete_python_app(app, remove_files=remove_files)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PythonAppStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        app = start_python_app(app)
        return Response({"success": True, "data": PythonAppSerializer(app).data})


class PythonAppStopView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        app = stop_python_app(app)
        return Response({"success": True, "data": PythonAppSerializer(app).data})


class PythonAppRestartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        app = restart_python_app(app)
        return Response({"success": True, "data": PythonAppSerializer(app).data})


class PythonAppInstallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        result = install_requirements(app)
        return Response({"success": True, "data": result})


class PythonAppLogsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        app = get_object_or_404(apps_qs(request.user), pk=pk)
        lines = int(request.query_params.get("lines", 100))
        return Response({"success": True, "data": read_logs(app, lines=min(lines, 1000))})
