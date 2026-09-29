"""API build / images / compose Docker."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.docker_mgmt.build_compose import (
    builds_qs,
    compose_down,
    compose_qs,
    compose_up,
    create_build_job,
    create_compose_project,
    list_local_images,
    pull_image,
    remove_compose_project,
    remove_local_image,
    write_dockerfile_template,
)
from apps.docker_mgmt.serializers import (
    DockerBuildCreateSerializer,
    DockerBuildJobSerializer,
    DockerComposeCreateSerializer,
    DockerComposeProjectSerializer,
    DockerDockerfileTemplateSerializer,
    DockerImagePullSerializer,
    DockerImageRemoveSerializer,
)
from apps.docker_mgmt.views import _resolve_owner


class DockerImageListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": list_local_images(request.user)})


class DockerImagePullView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = DockerImagePullSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = pull_image(
            request.user,
            serializer.validated_data["image"],
            serializer.validated_data.get("tag", "latest"),
        )
        return Response({"success": True, "data": data})


class DockerImageRemoveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = DockerImageRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        remove_local_image(
            request.user,
            serializer.validated_data["repository"],
            serializer.validated_data.get("tag", "latest"),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DockerBuildListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = builds_qs(request.user)[:50]
        return Response({"success": True, "data": DockerBuildJobSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = DockerBuildCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        job = create_build_job(
            owner=owner,
            name=data["name"],
            context_path=data["context_path"],
            dockerfile=data.get("dockerfile", "Dockerfile"),
            image_name=data.get("image_name", ""),
            tag=data.get("tag", "latest"),
            no_cache=data.get("no_cache", False),
        )
        return Response(
            {"success": True, "data": DockerBuildJobSerializer(job).data},
            status=status.HTTP_201_CREATED,
        )


class DockerBuildDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        job = get_object_or_404(builds_qs(request.user), pk=pk)
        return Response({"success": True, "data": DockerBuildJobSerializer(job).data})


class DockerComposeListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = compose_qs(request.user)
        return Response({"success": True, "data": DockerComposeProjectSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = DockerComposeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        project = create_compose_project(
            owner=owner,
            name=data["name"],
            project_path=data["project_path"],
            compose_file=data.get("compose_file", ""),
        )
        return Response(
            {"success": True, "data": DockerComposeProjectSerializer(project).data},
            status=status.HTTP_201_CREATED,
        )


class DockerComposeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        project = get_object_or_404(compose_qs(request.user), pk=pk)
        return Response({"success": True, "data": DockerComposeProjectSerializer(project).data})

    def delete(self, request: Request, pk: int) -> Response:
        project = get_object_or_404(compose_qs(request.user), pk=pk)
        remove_compose_project(project)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DockerComposeUpView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        project = get_object_or_404(compose_qs(request.user), pk=pk)
        build = bool(request.data.get("build", True))
        project = compose_up(project, build=build)
        return Response({"success": True, "data": DockerComposeProjectSerializer(project).data})


class DockerComposeDownView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        project = get_object_or_404(compose_qs(request.user), pk=pk)
        project = compose_down(project)
        return Response({"success": True, "data": DockerComposeProjectSerializer(project).data})


class DockerDockerfileTemplateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = DockerDockerfileTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        path = write_dockerfile_template(
            request.user,
            serializer.validated_data["context_path"],
            kind=serializer.validated_data.get("kind", "node"),
        )
        return Response({"success": True, "data": {"path": str(path.name), "full_path": str(path)}})
