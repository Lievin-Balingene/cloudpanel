"""API Sécurité avancée."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.permissions import IsAdministrator, IsResellerOrAdmin
from apps.security.models import AccountLockout, IpAccessRule, LoginAttempt
from apps.security.serializers import (
    AccountLockoutSerializer,
    IpAccessRuleCreateSerializer,
    IpAccessRuleSerializer,
    LoginAttemptSerializer,
    SecurityPolicySerializer,
    SecurityPolicyUpdateSerializer,
    SshKeyCreateSerializer,
)
from apps.security.services import (
    add_ssh_key,
    create_ip_rule,
    delete_ip_rule,
    delete_ssh_key,
    get_policy,
    list_ssh_keys,
    my_security_status,
    overview_for,
    unlock_key,
    update_policy,
)
from apps.security.smtp_restrictions import get_status as smtp_restrict_status
from apps.security.smtp_restrictions import set_enabled as smtp_restrict_set


class SshKeyListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": list_ssh_keys(request.user)})

    def post(self, request: Request) -> Response:
        serializer = SshKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = add_ssh_key(request.user, **serializer.validated_data)
        return Response(
            {"success": True, "data": key},
            status=status.HTTP_201_CREATED,
        )


class SshKeyDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, pk: int) -> Response:
        delete_ssh_key(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SecurityOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class SecurityPolicyView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": SecurityPolicySerializer(get_policy()).data})

    def patch(self, request: Request) -> Response:
        serializer = SecurityPolicyUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        policy = update_policy(**serializer.validated_data)
        return Response({"success": True, "data": SecurityPolicySerializer(policy).data})


class IpAccessRuleListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        qs = IpAccessRule.objects.all()
        return Response({"success": True, "data": IpAccessRuleSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = IpAccessRuleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = create_ip_rule(created_by=request.user, **serializer.validated_data)
        return Response(
            {"success": True, "data": IpAccessRuleSerializer(rule).data},
            status=status.HTTP_201_CREATED,
        )


class IpAccessRuleDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def delete(self, request: Request, pk: int) -> Response:
        rule = get_object_or_404(IpAccessRule, pk=pk)
        delete_ip_rule(rule)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginAttemptListView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        qs = LoginAttempt.objects.all()[:100]
        return Response({"success": True, "data": LoginAttemptSerializer(qs, many=True).data})


class AccountLockoutListView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        qs = AccountLockout.objects.all()[:100]
        return Response({"success": True, "data": AccountLockoutSerializer(qs, many=True).data})


class AccountUnlockView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        key = (request.data.get("key") or "").strip()
        if not key:
            return Response(
                {"success": False, "error": {"code": "missing_key", "message": "Clé requise."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ok = unlock_key(key)
        return Response({"success": True, "data": {"unlocked": ok}})


class ForcePasswordChangeView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def post(self, request: Request, pk: int) -> Response:
        user = get_object_or_404(User, pk=pk)
        if request.user.role == User.Role.RESELLER and user.parent_id != request.user.pk:
            return Response(status=status.HTTP_403_FORBIDDEN)
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])
        return Response({"success": True, "data": {"must_change_password": True}})


class MySecurityStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": my_security_status(request.user)})


class SmtpRestrictionsView(APIView):
    """WHM Security Center — SMTP Restrictions (bloquer by-pass MTA)."""

    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": smtp_restrict_status()})

    def post(self, request: Request) -> Response:
        enabled = request.data.get("enabled", None)
        if enabled is None:
            action = str(request.data.get("action") or "").lower()
            if action in {"enable", "on", "1", "true"}:
                enabled = True
            elif action in {"disable", "off", "0", "false"}:
                enabled = False
            else:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "invalid_action",
                            "message": "Spécifiez enabled=true|false ou action=enable|disable.",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        data = smtp_restrict_set(bool(enabled))
        return Response({"success": True, "data": data})
