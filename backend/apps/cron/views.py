"""API Cron Jobs."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.cron.serializers import (
    CronJobCreateSerializer,
    CronJobSerializer,
    CronJobUpdateSerializer,
)
from apps.cron.services import (
    create_cron_job,
    crontab_preview_for,
    delete_cron_job,
    jobs_queryset_for,
    overview_for,
    request_cron_sync,
    update_cron_job,
)


class CronJobListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = jobs_queryset_for(request.user)
        return Response({"success": True, "data": CronJobSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = CronJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        owner = request.user
        if data.get("owner_id") and request.user.role in {
            User.Role.ADMINISTRATOR,
            User.Role.RESELLER,
        }:
            owner = get_object_or_404(User, pk=data["owner_id"])
            if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
                return Response(status=status.HTTP_403_FORBIDDEN)
        job = create_cron_job(
            owner=owner,
            command=data["command"],
            common=data.get("common", "custom"),
            minute=data.get("minute", "0"),
            hour=data.get("hour", "*"),
            day=data.get("day", "*"),
            month=data.get("month", "*"),
            weekday=data.get("weekday", "*"),
            email_to=data.get("email_to", ""),
            label=data.get("label", ""),
            is_active=data.get("is_active", True),
        )
        return Response(
            {"success": True, "data": CronJobSerializer(job).data},
            status=status.HTTP_201_CREATED,
        )


class CronJobDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        job = get_object_or_404(jobs_queryset_for(request.user), pk=pk)
        return Response({"success": True, "data": CronJobSerializer(job).data})

    def patch(self, request: Request, pk: int) -> Response:
        job = get_object_or_404(jobs_queryset_for(request.user), pk=pk)
        serializer = CronJobUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        job = update_cron_job(job, **serializer.validated_data)
        return Response({"success": True, "data": CronJobSerializer(job).data})

    def delete(self, request: Request, pk: int) -> Response:
        job = get_object_or_404(jobs_queryset_for(request.user), pk=pk)
        delete_cron_job(job)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CronOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class CronPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        owner = request.user
        owner_id = request.query_params.get("owner_id")
        if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
            owner = get_object_or_404(User, pk=int(owner_id))
            if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
                return Response(status=status.HTTP_403_FORBIDDEN)
        return Response(
            {
                "success": True,
                "data": {
                    "crontab": crontab_preview_for(owner),
                    "filename": f"vzone-{(owner.system_username or owner.username).lower()}",
                },
            }
        )


class CronSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        owner = request.user
        owner_id = request.data.get("owner_id")
        if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
            owner = get_object_or_404(User, pk=int(owner_id))
            if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
                return Response(status=status.HTTP_403_FORBIDDEN)
        result = request_cron_sync(owner)
        return Response({"success": True, "data": result})
