from __future__ import annotations

from rest_framework import serializers

from apps.monitoring.models import AlertEvent, AlertRule


class AlertRuleSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
        default="",
    )

    class Meta:
        model = AlertRule
        fields = (
            "id",
            "name",
            "metric",
            "operator",
            "threshold",
            "service_name",
            "severity",
            "cooldown_minutes",
            "notify_email",
            "recipients",
            "is_active",
            "last_triggered_at",
            "notes",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "last_triggered_at",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )


class AlertRuleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    metric = serializers.ChoiceField(choices=[c.value for c in AlertRule.Metric])
    operator = serializers.ChoiceField(
        choices=[c.value for c in AlertRule.Operator],
        default="gte",
    )
    threshold = serializers.FloatField(default=90.0)
    service_name = serializers.CharField(required=False, allow_blank=True, default="")
    severity = serializers.ChoiceField(
        choices=[c.value for c in AlertRule.Severity],
        default="warning",
    )
    cooldown_minutes = serializers.IntegerField(required=False, min_value=0, default=30)
    notify_email = serializers.BooleanField(required=False, default=True)
    recipients = serializers.CharField(required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class AlertRuleUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=120)
    metric = serializers.ChoiceField(
        choices=[c.value for c in AlertRule.Metric],
        required=False,
    )
    operator = serializers.ChoiceField(
        choices=[c.value for c in AlertRule.Operator],
        required=False,
    )
    threshold = serializers.FloatField(required=False)
    service_name = serializers.CharField(required=False, allow_blank=True)
    severity = serializers.ChoiceField(
        choices=[c.value for c in AlertRule.Severity],
        required=False,
    )
    cooldown_minutes = serializers.IntegerField(required=False, min_value=0)
    notify_email = serializers.BooleanField(required=False)
    recipients = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class AlertEventSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    rule_metric = serializers.CharField(source="rule.metric", read_only=True)
    rule_severity = serializers.CharField(source="rule.severity", read_only=True)
    acknowledged_by_username = serializers.CharField(
        source="acknowledged_by.username",
        read_only=True,
        default="",
    )

    class Meta:
        model = AlertEvent
        fields = (
            "id",
            "rule",
            "rule_name",
            "rule_metric",
            "rule_severity",
            "status",
            "metric_value",
            "message",
            "notified",
            "notified_at",
            "acknowledged_at",
            "acknowledged_by",
            "acknowledged_by_username",
            "resolved_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
