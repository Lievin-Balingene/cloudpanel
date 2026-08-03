"""API PHP multi-version."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.php.serializers import (
    PhpSelectorCreateSerializer,
    PhpSelectorSerializer,
    PhpSelectorUpdateSerializer,
    PhpVersionSerializer,
)
from apps.php.services import (
    create_selector,
    delete_selector,
    discover_system_versions,
    ensure_default_versions,
    overview_for,
    selectors_qs,
    set_default_version,
    update_selector,
    versions_qs,
)


def _resolve_owner(request: Request, owner_id: int | None) -> User:
    owner = request.user
    if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
        owner = get_object_or_404(User, pk=owner_id)
        if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
            raise PermissionError
    return owner


class PhpOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class PhpVersionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        ensure_default_versions()
        qs = versions_qs()
        return Response({"success": True, "data": PhpVersionSerializer(qs, many=True).data})


class PhpVersionDiscoverView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        if request.user.role != User.Role.ADMINISTRATOR:
            return Response(status=status.HTTP_403_FORBIDDEN)
        versions = discover_system_versions()
        return Response({"success": True, "data": PhpVersionSerializer(versions, many=True).data})


class PhpVersionDefaultView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        if request.user.role != User.Role.ADMINISTRATOR:
            return Response(status=status.HTTP_403_FORBIDDEN)
        version = set_default_version(pk)
        return Response({"success": True, "data": PhpVersionSerializer(version).data})


class PhpSelectorListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        ensure_default_versions()
        qs = selectors_qs(request.user)
        return Response({"success": True, "data": PhpSelectorSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = PhpSelectorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        selector = create_selector(
            owner=owner,
            php_version_id=data["php_version_id"],
            relative_path=data.get("relative_path", "public_html"),
            domain_name=data.get("domain_name", ""),
            handler=data.get("handler", "fpm"),
            ini_settings=data.get("ini_settings") or None,
            extensions=data.get("extensions") or None,
            notes=data.get("notes", ""),
        )
        return Response(
            {"success": True, "data": PhpSelectorSerializer(selector).data},
            status=status.HTTP_201_CREATED,
        )


class PhpSelectorDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        selector = get_object_or_404(selectors_qs(request.user), pk=pk)
        return Response({"success": True, "data": PhpSelectorSerializer(selector).data})

    def patch(self, request: Request, pk: int) -> Response:
        selector = get_object_or_404(selectors_qs(request.user), pk=pk)
        serializer = PhpSelectorUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        selector = update_selector(selector, **serializer.validated_data)
        return Response({"success": True, "data": PhpSelectorSerializer(selector).data})

    def delete(self, request: Request, pk: int) -> Response:
        selector = get_object_or_404(selectors_qs(request.user), pk=pk)
        delete_selector(selector)
        return Response(status=status.HTTP_204_NO_CONTENT)
