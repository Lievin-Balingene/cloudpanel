"""API FTP."""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.ftp.models import FtpAccount, FtpLog
from apps.ftp.serializers import (
    FtpAccountCreateSerializer,
    FtpAccountSerializer,
    FtpAccountUpdateSerializer,
    FtpAuthSerializer,
    FtpLogCreateSerializer,
    FtpLogSerializer,
)
from apps.ftp.services import (
    accounts_queryset_for,
    authenticate_ftp,
    create_ftp_account,
    delete_ftp_account,
    logs_queryset_for,
    record_log,
    suspend_ftp_account,
    update_ftp_account,
)


class FtpAuthThrottle(AnonRateThrottle):
    scope = "auth"


def _check_ftp_secret(request: Request) -> bool:
    configured = getattr(settings, "VZONE_FTP_AUTH_SECRET", "")
    if not configured:
        return True
    secret = request.headers.get("X-Vzone-Ftp-Secret") or request.data.get("secret")
    return secret == configured


class FtpAccountListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = accounts_queryset_for(request.user)
        return Response({"success": True, "data": FtpAccountSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = FtpAccountCreateSerializer(data=request.data)
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
        account = create_ftp_account(
            owner=owner,
            username=data["username"],
            password=data["password"],
            relative_directory=data.get("relative_directory", "public_html"),
            quota_mb=data.get("quota_mb", 0),
            bandwidth_kbs=data.get("bandwidth_kbs", 0),
            can_write=data.get("can_write", True),
            notes=data.get("notes", ""),
        )
        return Response(
            {"success": True, "data": FtpAccountSerializer(account).data},
            status=status.HTTP_201_CREATED,
        )


class FtpAccountDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        account = get_object_or_404(accounts_queryset_for(request.user), pk=pk)
        return Response({"success": True, "data": FtpAccountSerializer(account).data})

    def patch(self, request: Request, pk: int) -> Response:
        account = get_object_or_404(accounts_queryset_for(request.user), pk=pk)
        serializer = FtpAccountUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        account = update_ftp_account(account, **serializer.validated_data)
        return Response({"success": True, "data": FtpAccountSerializer(account).data})

    def delete(self, request: Request, pk: int) -> Response:
        account = get_object_or_404(accounts_queryset_for(request.user), pk=pk)
        remove_dir = str(request.query_params.get("remove_directory", "false")).lower() in {
            "1",
            "true",
            "yes",
        }
        delete_ftp_account(account, remove_directory=remove_dir)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FtpSuspendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        account = get_object_or_404(accounts_queryset_for(request.user), pk=pk)
        suspended = bool(request.data.get("suspended", True))
        account = suspend_ftp_account(account, suspended=suspended)
        return Response({"success": True, "data": FtpAccountSerializer(account).data})


class FtpLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = logs_queryset_for(request.user)
        username = request.query_params.get("username")
        event_type = request.query_params.get("event_type")
        account_id = request.query_params.get("account_id")
        if username:
            qs = qs.filter(username__iexact=username)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if account_id:
            qs = qs.filter(account_id=account_id)
        limit = min(int(request.query_params.get("limit", 100)), 500)
        qs = qs[:limit]
        return Response({"success": True, "data": FtpLogSerializer(qs, many=True).data})


class FtpAuthView(APIView):
    """Endpoint interne pour daemon FTP / health auth."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [FtpAuthThrottle]

    def post(self, request: Request) -> Response:
        if not _check_ftp_secret(request):
            return Response(status=status.HTTP_403_FORBIDDEN)
        serializer = FtpAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = authenticate_ftp(
            serializer.validated_data["username"],
            serializer.validated_data["password"],
            serializer.validated_data.get("ip_address"),
        )
        if account is None:
            return Response(
                {
                    "success": False,
                    "error": {"code": "auth_failed", "message": "Identifiants invalides."},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(
            {
                "success": True,
                "data": {
                    "username": account.username,
                    "directory": account.directory,
                    "can_write": account.can_write,
                    "quota_mb": account.quota_mb,
                    "bandwidth_kbs": account.bandwidth_kbs,
                },
            }
        )


class FtpLogIngestView(APIView):
    """Ingestion de logs depuis Pure-FTPd / ProFTPD / script."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [FtpAuthThrottle]

    def post(self, request: Request) -> Response:
        if not _check_ftp_secret(request):
            return Response(status=status.HTTP_403_FORBIDDEN)
        serializer = FtpLogCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account = FtpAccount.objects.filter(username__iexact=data["username"]).first()
        log = record_log(
            event_type=data["event_type"],
            account=account,
            owner=account.owner if account else None,
            username=data["username"],
            path=data.get("path", ""),
            bytes_transferred=data.get("bytes_transferred", 0),
            ip_address=data.get("ip_address"),
            message=data.get("message", ""),
            success=data.get("success", True),
        )
        return Response(
            {"success": True, "data": FtpLogSerializer(log).data},
            status=status.HTTP_201_CREATED,
        )


class FtpStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        accounts = accounts_queryset_for(request.user)
        logs = logs_queryset_for(request.user)
        since = timezone.now() - timedelta(hours=24)
        return Response(
            {
                "success": True,
                "data": {
                    "accounts_total": accounts.count(),
                    "accounts_active": accounts.filter(is_active=True, is_suspended=False).count(),
                    "accounts_suspended": accounts.filter(is_suspended=True).count(),
                    "failed_logins_24h": logs.filter(
                        event_type=FtpLog.EventType.LOGIN_FAILED,
                        created_at__gte=since,
                    ).count(),
                },
            }
        )
