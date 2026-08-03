"""API Backups."""
from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.backups.models import BackupEventLog
from apps.backups.serializers import (
    BackupArchiveCreateSerializer,
    BackupArchiveSerializer,
    BackupEventLogSerializer,
    BackupScheduleSerializer,
    BackupScheduleUpsertSerializer,
)
from apps.backups.services import (
    archives_qs,
    create_backup,
    delete_backup,
    delete_schedule,
    download_info,
    overview_for,
    restore_backup,
    schedules_qs,
    upsert_schedule,
)


def _resolve_owner(request: Request, owner_id: int | None) -> User:
    owner = request.user
    if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
        owner = get_object_or_404(User, pk=owner_id)
        if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
            raise PermissionError
    return owner


class BackupOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class BackupArchiveListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = archives_qs(request.user)
        return Response({"success": True, "data": BackupArchiveSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = BackupArchiveCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        archive = create_backup(
            owner=owner,
            name=data.get("name") or "",
            label=data.get("label", ""),
            backup_type=data.get("backup_type", "full"),
            includes=data.get("includes") or [],
            notes=data.get("notes", ""),
        )
        return Response(
            {"success": True, "data": BackupArchiveSerializer(archive).data},
            status=status.HTTP_201_CREATED,
        )


class BackupArchiveDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        archive = get_object_or_404(archives_qs(request.user), pk=pk)
        return Response({"success": True, "data": BackupArchiveSerializer(archive).data})

    def delete(self, request: Request, pk: int) -> Response:
        archive = get_object_or_404(archives_qs(request.user), pk=pk)
        delete_backup(archive)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BackupRestoreView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        archive = get_object_or_404(archives_qs(request.user), pk=pk)
        archive = restore_backup(archive, actor=request.user)
        return Response({"success": True, "data": BackupArchiveSerializer(archive).data})


class BackupDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        archive = get_object_or_404(archives_qs(request.user), pk=pk)
        return Response({"success": True, "data": download_info(archive)})


class BackupScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = schedules_qs(request.user)
        return Response({"success": True, "data": BackupScheduleSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = BackupScheduleUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        schedule = upsert_schedule(
            owner=owner,
            frequency=data.get("frequency", "weekly"),
            includes=data.get("includes") or [],
            hour=data.get("hour", 2),
            weekday=data.get("weekday", 0),
            is_active=data.get("is_active", True),
            notes=data.get("notes", ""),
        )
        return Response(
            {"success": True, "data": BackupScheduleSerializer(schedule).data},
            status=status.HTTP_201_CREATED,
        )


class BackupScheduleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, pk: int) -> Response:
        schedule = get_object_or_404(schedules_qs(request.user), pk=pk)
        serializer = BackupScheduleUpsertSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        schedule = upsert_schedule(
            owner=schedule.owner,
            frequency=data.get("frequency", schedule.frequency),
            includes=data.get("includes", schedule.includes),
            hour=data.get("hour", schedule.hour),
            weekday=data.get("weekday", schedule.weekday),
            is_active=data.get("is_active", schedule.is_active),
            notes=data.get("notes", schedule.notes),
        )
        return Response({"success": True, "data": BackupScheduleSerializer(schedule).data})

    def delete(self, request: Request, pk: int) -> Response:
        schedule = get_object_or_404(schedules_qs(request.user), pk=pk)
        delete_schedule(schedule)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BackupEventLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        if request.user.role == User.Role.ADMINISTRATOR:
            qs = BackupEventLog.objects.select_related("archive", "owner")
        elif request.user.role == User.Role.RESELLER:
            qs = BackupEventLog.objects.filter(
                Q(owner=request.user) | Q(owner__parent=request.user)
            ).select_related("archive", "owner")
        else:
            qs = BackupEventLog.objects.filter(owner=request.user).select_related("archive", "owner")
        archive_id = request.query_params.get("archive_id")
        if archive_id:
            qs = qs.filter(archive_id=archive_id)
        qs = qs[:100]
        return Response({"success": True, "data": BackupEventLogSerializer(qs, many=True).data})
