"""API contexte local — exploitation, pas facturation."""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.permissions import IsAdministrator, IsResellerOrAdmin
from apps.local_context.serializers import LocalSiteProfileSerializer
from apps.local_context.services import (
    apply_country_defaults,
    compose_notice,
    get_profile,
    overview,
    profile_payload,
)


class LocalProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": profile_payload()})

    def patch(self, request: Request) -> Response:
        if request.user.role != User.Role.ADMINISTRATOR:
            return Response(status=status.HTTP_403_FORBIDDEN)
        profile = get_profile()
        country = request.data.get("country")
        if country and country != profile.country and request.data.get("apply_country_defaults"):
            apply_country_defaults(profile, str(country))
        serializer = LocalSiteProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "data": profile_payload()})


class LocalOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview()})


class LocalRecoverView(APIView):
    """Après une coupure : relance nginx, API, redis, mail via l’agent de réparation."""

    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        from apps.server_setup.repairs import enqueue_repair

        payload = enqueue_repair(
            script_id="after-outage",
            requested_by=request.user.username,
        )
        return Response({"success": True, "data": payload})


class LocalNoticeView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        user_id = request.query_params.get("user_id")
        kind = request.query_params.get("kind") or "welcome"
        if kind not in {"welcome", "disk", "ssl", "outage"}:
            kind = "welcome"
        target = User.objects.filter(pk=user_id).first() if user_id else None
        if not target:
            return Response(
                {"success": False, "error": {"code": "not_found", "message": "Compte introuvable."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if request.user.role == User.Role.RESELLER and target.parent_id != request.user.pk:
            return Response(status=status.HTTP_403_FORBIDDEN)
        return Response({"success": True, "data": compose_notice(target, kind)})
