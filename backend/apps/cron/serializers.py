from __future__ import annotations

from rest_framework import serializers

from apps.cron.models import CronJob


class CronJobSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    schedule_line = serializers.CharField(read_only=True)

    class Meta:
        model = CronJob
        fields = (
            "id",
            "owner",
            "owner_username",
            "common",
            "minute",
            "hour",
            "day",
            "month",
            "weekday",
            "schedule_line",
            "command",
            "email_to",
            "label",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "owner", "created_at", "updated_at")


class CronJobCreateSerializer(serializers.Serializer):
    owner_id = serializers.IntegerField(required=False)
    common = serializers.ChoiceField(
        choices=CronJob.Common.choices,
        required=False,
        default=CronJob.Common.CUSTOM,
    )
    minute = serializers.CharField(required=False, default="0", max_length=64)
    hour = serializers.CharField(required=False, default="*", max_length=64)
    day = serializers.CharField(required=False, default="*", max_length=64)
    month = serializers.CharField(required=False, default="*", max_length=64)
    weekday = serializers.CharField(required=False, default="*", max_length=64)
    command = serializers.CharField(max_length=4000)
    email_to = serializers.EmailField(required=False, allow_blank=True, default="")
    label = serializers.CharField(required=False, allow_blank=True, default="", max_length=120)
    is_active = serializers.BooleanField(required=False, default=True)


class CronJobUpdateSerializer(serializers.Serializer):
    common = serializers.ChoiceField(choices=CronJob.Common.choices, required=False)
    minute = serializers.CharField(required=False, max_length=64)
    hour = serializers.CharField(required=False, max_length=64)
    day = serializers.CharField(required=False, max_length=64)
    month = serializers.CharField(required=False, max_length=64)
    weekday = serializers.CharField(required=False, max_length=64)
    command = serializers.CharField(required=False, max_length=4000)
    email_to = serializers.EmailField(required=False, allow_blank=True)
    label = serializers.CharField(required=False, allow_blank=True, max_length=120)
    is_active = serializers.BooleanField(required=False)
