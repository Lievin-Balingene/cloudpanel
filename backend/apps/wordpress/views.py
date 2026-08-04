"""API WordPress."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.wordpress.serializers import WordPressInstallSerializer, WordPressSiteSerializer
from apps.wordpress.services import (
    delete_wordpress,
    install_wordpress,
    overview_for,
    sites_qs,
)


def _resolve_owner(request: Request, owner_id: int | None) -> User:
    owner = request.user
    if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
        owner = get_object_or_404(User, pk=owner_id)
        if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
            raise PermissionError
    return owner


class WordPressOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class WordPressSiteListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = sites_qs(request.user)
        return Response({"success": True, "data": WordPressSiteSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = WordPressInstallSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)

        site, admin_password = install_wordpress(
            owner=owner,
            domain_id=data["domain_id"],
            title=data.get("title") or "Mon site",
            admin_user=data.get("admin_user") or "admin",
            admin_email=data.get("admin_email") or "",
            admin_password=data.get("admin_password") or "",
            locale=data.get("locale") or "fr_FR",
        )
        payload = WordPressSiteSerializer(site).data
        payload["admin_password"] = admin_password
        return Response({"success": True, "data": payload}, status=status.HTTP_201_CREATED)


class WordPressSiteDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        site = get_object_or_404(sites_qs(request.user), pk=pk)
        return Response({"success": True, "data": WordPressSiteSerializer(site).data})

    def delete(self, request: Request, pk: int) -> Response:
        site = get_object_or_404(sites_qs(request.user), pk=pk)
        remove_files = str(request.query_params.get("remove_files", "true")).lower() in {
            "1",
            "true",
            "yes",
        }
        remove_database = str(request.query_params.get("remove_database", "true")).lower() in {
            "1",
            "true",
            "yes",
        }
        delete_wordpress(site, remove_files=remove_files, remove_database=remove_database)
        return Response(status=status.HTTP_204_NO_CONTENT)
