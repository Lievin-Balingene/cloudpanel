"""API Sécurité avancée."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.permissions import IsResellerOrAdmin
from apps.security.models import AccountLockout, IpAccessRule, LoginAttempt
from apps.security.serializers import (
    AccountLockoutSerializer,
    IpAccessRuleCreateSerializer,
    IpAccessRuleSerializer,
    LoginAttemptSerializer,
    SecurityPolicySerializer,
    SecurityPolicyUpdateSerializer,
)
from apps.security.services import (
    create_ip_rule,
    delete_ip_rule,
    get_policy,
    my_security_status,
    overview_for,
    unlock_key,
    update_policy,
)


class SecurityOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class SecurityPolicyView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": SecurityPolicySerializer(get_policy()).data})

    def patch(self, request: Request) -> Response:
        serializer = SecurityPolicyUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        policy = update_policy(**serializer.validated_data)
        return Response({"success": True, "data": SecurityPolicySerializer(policy).data})


class IpAccessRuleListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

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
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def delete(self, request: Request, pk: int) -> Response:
        rule = get_object_or_404(IpAccessRule, pk=pk)
        delete_ip_rule(rule)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginAttemptListView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        qs = LoginAttempt.objects.all()[:100]
        return Response({"success": True, "data": LoginAttemptSerializer(qs, many=True).data})


class AccountLockoutListView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        qs = AccountLockout.objects.all()[:100]
        return Response({"success": True, "data": AccountLockoutSerializer(qs, many=True).data})


class AccountUnlockView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

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
