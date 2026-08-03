"""API Git Deploy."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.git_deploy.models import GitRepository
from apps.git_deploy.serializers import (
    GitDeployLogSerializer,
    GitRepositoryCreateSerializer,
    GitRepositorySerializer,
    GitRepositoryUpdateSerializer,
)
from apps.git_deploy.services import (
    clone_repository,
    create_repository,
    delete_repository,
    generate_deploy_key,
    logs_qs,
    overview_for,
    pull_repository,
    repos_qs,
    rotate_webhook_token,
    run_deploy_script,
    update_repository,
    webhook_deploy,
)


def _resolve_owner(request: Request, owner_id: int | None) -> User:
    owner = request.user
    if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
        owner = get_object_or_404(User, pk=owner_id)
        if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
            raise PermissionError
    return owner


class GitOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class GitRepositoryListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = repos_qs(request.user)
        return Response({"success": True, "data": GitRepositorySerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = GitRepositoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        repo = create_repository(
            owner=owner,
            name=data["name"],
            remote_url=data["remote_url"],
            branch=data.get("branch", "main"),
            relative_path=data.get("relative_path", ""),
            deploy_script=data.get("deploy_script", ""),
            auto_deploy=data.get("auto_deploy", True),
            label=data.get("label", ""),
            notes=data.get("notes", ""),
            clone_now=data.get("clone_now", True),
        )
        return Response(
            {"success": True, "data": GitRepositorySerializer(repo).data},
            status=status.HTTP_201_CREATED,
        )


class GitRepositoryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        repo = get_object_or_404(repos_qs(request.user), pk=pk)
        return Response({"success": True, "data": GitRepositorySerializer(repo).data})

    def patch(self, request: Request, pk: int) -> Response:
        repo = get_object_or_404(repos_qs(request.user), pk=pk)
        serializer = GitRepositoryUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        repo = update_repository(repo, **serializer.validated_data)
        return Response({"success": True, "data": GitRepositorySerializer(repo).data})

    def delete(self, request: Request, pk: int) -> Response:
        repo = get_object_or_404(repos_qs(request.user), pk=pk)
        remove_files = str(request.query_params.get("remove_files", "false")).lower() in {
            "1",
            "true",
            "yes",
        }
        delete_repository(repo, remove_files=remove_files)
        return Response(status=status.HTTP_204_NO_CONTENT)


class GitCloneView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        repo = get_object_or_404(repos_qs(request.user), pk=pk)
        repo = clone_repository(repo)
        return Response({"success": True, "data": GitRepositorySerializer(repo).data})


class GitPullView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        repo = get_object_or_404(repos_qs(request.user), pk=pk)
        repo = pull_repository(repo)
        return Response({"success": True, "data": GitRepositorySerializer(repo).data})


class GitDeployView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        repo = get_object_or_404(repos_qs(request.user), pk=pk)
        repo = run_deploy_script(repo)
        return Response({"success": True, "data": GitRepositorySerializer(repo).data})


class GitKeygenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        repo = get_object_or_404(repos_qs(request.user), pk=pk)
        repo = generate_deploy_key(repo)
        return Response({"success": True, "data": GitRepositorySerializer(repo).data})


class GitRotateWebhookView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        repo = get_object_or_404(repos_qs(request.user), pk=pk)
        repo = rotate_webhook_token(repo)
        return Response({"success": True, "data": GitRepositorySerializer(repo).data})


class GitLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = logs_qs(request.user)[:100]
        repo_id = request.query_params.get("repository_id")
        if repo_id:
            qs = logs_qs(request.user).filter(repository_id=repo_id)[:100]
        return Response({"success": True, "data": GitDeployLogSerializer(qs, many=True).data})


class GitWebhookView(APIView):
    """Endpoint public authentifié par token dans l'URL."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request, token: str) -> Response:
        repo = get_object_or_404(GitRepository, webhook_token=token, is_active=True)
        repo = webhook_deploy(repo, token=token)
        return Response({"success": True, "data": {"repository": repo.name, "status": repo.status}})
