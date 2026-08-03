"""API Firewall & Fail2Ban."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsResellerOrAdmin
from apps.firewall.models import Fail2BanBan, Fail2BanJail, FirewallEventLog, FirewallRule
from apps.firewall.serializers import (
    BanIpSerializer,
    Fail2BanBanSerializer,
    Fail2BanJailSerializer,
    FirewallEventLogSerializer,
    FirewallRuleCreateSerializer,
    FirewallRuleSerializer,
    FirewallRuleUpdateSerializer,
    UnbanIpSerializer,
)
from apps.firewall.services import (
    apply_rule,
    ban_ip,
    create_rule,
    delete_rule,
    ensure_default_jails,
    overview_for,
    sync_fail2ban,
    unban_ip,
    update_rule,
)


class FirewallOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class FirewallRuleListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        qs = FirewallRule.objects.all()
        return Response({"success": True, "data": FirewallRuleSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = FirewallRuleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        rule = create_rule(created_by=request.user, **data)
        return Response(
            {"success": True, "data": FirewallRuleSerializer(rule).data},
            status=status.HTTP_201_CREATED,
        )


class FirewallRuleDetailView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request, pk: int) -> Response:
        rule = get_object_or_404(FirewallRule, pk=pk)
        return Response({"success": True, "data": FirewallRuleSerializer(rule).data})

    def patch(self, request: Request, pk: int) -> Response:
        rule = get_object_or_404(FirewallRule, pk=pk)
        serializer = FirewallRuleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        rule = update_rule(rule, **serializer.validated_data)
        return Response({"success": True, "data": FirewallRuleSerializer(rule).data})

    def delete(self, request: Request, pk: int) -> Response:
        rule = get_object_or_404(FirewallRule, pk=pk)
        delete_rule(rule, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FirewallRuleApplyView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def post(self, request: Request, pk: int) -> Response:
        rule = get_object_or_404(FirewallRule, pk=pk)
        rule = apply_rule(rule, actor=request.user)
        return Response({"success": True, "data": FirewallRuleSerializer(rule).data})


class Fail2BanJailListView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        sync = request.query_params.get("sync", "0") == "1"
        if sync:
            jails = sync_fail2ban(actor=request.user)
        else:
            ensure_default_jails()
            jails = list(Fail2BanJail.objects.all())
        return Response({"success": True, "data": Fail2BanJailSerializer(jails, many=True).data})


class Fail2BanBanListView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        qs = Fail2BanBan.objects.select_related("jail", "created_by")
        status_filter = request.query_params.get("status", "active")
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)
        jail_name = request.query_params.get("jail")
        if jail_name:
            qs = qs.filter(jail__name=jail_name)
        qs = qs[:100]
        return Response({"success": True, "data": Fail2BanBanSerializer(qs, many=True).data})


class Fail2BanBanView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def post(self, request: Request) -> Response:
        serializer = BanIpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ban = ban_ip(
            ip_address=data["ip_address"],
            jail_name=data.get("jail_name") or "sshd",
            reason=data.get("reason", ""),
            actor=request.user,
        )
        return Response(
            {"success": True, "data": Fail2BanBanSerializer(ban).data},
            status=status.HTTP_201_CREATED,
        )


class Fail2BanUnbanView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def post(self, request: Request) -> Response:
        serializer = UnbanIpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        count = unban_ip(
            ip_address=data["ip_address"],
            jail_name=data.get("jail_name") or None,
            actor=request.user,
        )
        return Response({"success": True, "data": {"unbanned": count}})


class Fail2BanSyncView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def post(self, request: Request) -> Response:
        jails = sync_fail2ban(actor=request.user)
        return Response({"success": True, "data": Fail2BanJailSerializer(jails, many=True).data})


class FirewallEventLogListView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        qs = FirewallEventLog.objects.select_related("actor")[:100]
        return Response({"success": True, "data": FirewallEventLogSerializer(qs, many=True).data})
