"""API Docker."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.docker_mgmt.models import DockerContainer, DockerContainerLog
from apps.docker_mgmt.serializers import (
    DockerContainerCreateSerializer,
    DockerContainerLogSerializer,
    DockerContainerSerializer,
    DockerContainerUpdateSerializer,
)
from apps.docker_mgmt.services import (
    containers_qs,
    create_container,
    overview_for,
    read_container_logs,
    remove_container,
    restart_container,
    start_container,
    stop_container,
    update_container,
)


def _resolve_owner(request: Request, owner_id: int | None) -> User:
    owner = request.user
    if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
        owner = get_object_or_404(User, pk=owner_id)
        if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
            raise PermissionError
    return owner


class DockerOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class DockerContainerListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = containers_qs(request.user).exclude(status=DockerContainer.Status.REMOVED)
        return Response({"success": True, "data": DockerContainerSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = DockerContainerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        container = create_container(
            owner=owner,
            name=data["name"],
            image=data["image"],
            tag=data.get("tag", "latest"),
            ports=data.get("ports") or {},
            env_vars=data.get("env_vars") or {},
            volumes=data.get("volumes") or [],
            command=data.get("command", ""),
            restart_policy=data.get("restart_policy", "unless-stopped"),
            memory_mb=data.get("memory_mb", 512),
            cpus=data.get("cpus", 1),
            label=data.get("label", ""),
            notes=data.get("notes", ""),
            start_now=data.get("start_now", True),
        )
        return Response(
            {"success": True, "data": DockerContainerSerializer(container).data},
            status=status.HTTP_201_CREATED,
        )


class DockerContainerDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        container = get_object_or_404(containers_qs(request.user), pk=pk)
        return Response({"success": True, "data": DockerContainerSerializer(container).data})

    def patch(self, request: Request, pk: int) -> Response:
        container = get_object_or_404(containers_qs(request.user), pk=pk)
        serializer = DockerContainerUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        container = update_container(container, **serializer.validated_data)
        return Response({"success": True, "data": DockerContainerSerializer(container).data})

    def delete(self, request: Request, pk: int) -> Response:
        container = get_object_or_404(containers_qs(request.user), pk=pk)
        remove_container(container)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DockerStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        container = get_object_or_404(containers_qs(request.user), pk=pk)
        container = start_container(container)
        return Response({"success": True, "data": DockerContainerSerializer(container).data})


class DockerStopView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        container = get_object_or_404(containers_qs(request.user), pk=pk)
        container = stop_container(container)
        return Response({"success": True, "data": DockerContainerSerializer(container).data})


class DockerRestartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        container = get_object_or_404(containers_qs(request.user), pk=pk)
        container = restart_container(container)
        return Response({"success": True, "data": DockerContainerSerializer(container).data})


class DockerLogsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        container = get_object_or_404(containers_qs(request.user), pk=pk)
        tail = int(request.query_params.get("tail", 100))
        return Response({"success": True, "data": {"logs": read_container_logs(container, tail=tail)}})


class DockerEventLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = DockerContainerLog.objects.filter(
            container__in=containers_qs(request.user)
        ).select_related("container")[:100]
        container_id = request.query_params.get("container_id")
        if container_id:
            qs = DockerContainerLog.objects.filter(
                container__in=containers_qs(request.user),
                container_id=container_id,
            )[:100]
        return Response({"success": True, "data": DockerContainerLogSerializer(qs, many=True).data})
