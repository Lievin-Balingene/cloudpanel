"""API Monitoring & Alertes."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdministrator
from apps.monitoring.models import AlertEvent, AlertRule
from apps.monitoring.serializers import (
    AlertEventSerializer,
    AlertRuleCreateSerializer,
    AlertRuleSerializer,
    AlertRuleUpdateSerializer,
)
from apps.monitoring.services import (
    acknowledge_event,
    create_rule,
    delete_rule,
    evaluate_rules,
    overview_for,
    resolve_event,
    update_rule,
)


class MonitoringOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class AlertRuleListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        qs = AlertRule.objects.all()
        return Response({"success": True, "data": AlertRuleSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = AlertRuleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        rule = create_rule(created_by=request.user, **data)
        return Response(
            {"success": True, "data": AlertRuleSerializer(rule).data},
            status=status.HTTP_201_CREATED,
        )


class AlertRuleDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request, pk: int) -> Response:
        rule = get_object_or_404(AlertRule, pk=pk)
        return Response({"success": True, "data": AlertRuleSerializer(rule).data})

    def patch(self, request: Request, pk: int) -> Response:
        rule = get_object_or_404(AlertRule, pk=pk)
        serializer = AlertRuleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        rule = update_rule(rule, **serializer.validated_data)
        return Response({"success": True, "data": AlertRuleSerializer(rule).data})

    def delete(self, request: Request, pk: int) -> Response:
        rule = get_object_or_404(AlertRule, pk=pk)
        delete_rule(rule)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlertEventListView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        qs = AlertEvent.objects.select_related("rule", "acknowledged_by")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        rule_id = request.query_params.get("rule_id")
        if rule_id:
            qs = qs.filter(rule_id=rule_id)
        qs = qs[:100]
        return Response({"success": True, "data": AlertEventSerializer(qs, many=True).data})


class AlertEventAcknowledgeView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request, pk: int) -> Response:
        event = get_object_or_404(AlertEvent.objects.select_related("rule"), pk=pk)
        event = acknowledge_event(event, user=request.user)
        return Response({"success": True, "data": AlertEventSerializer(event).data})


class AlertEventResolveView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request, pk: int) -> Response:
        event = get_object_or_404(AlertEvent.objects.select_related("rule"), pk=pk)
        event = resolve_event(event)
        return Response({"success": True, "data": AlertEventSerializer(event).data})


class MonitoringEvaluateView(APIView):
    """Évaluation manuelle des règles (WHM)."""

    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        result = evaluate_rules()
        return Response({"success": True, "data": result})
