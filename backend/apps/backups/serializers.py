from __future__ import annotations

from rest_framework import serializers

from apps.backups.models import BackupArchive, BackupEventLog, BackupSchedule


class BackupArchiveSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = BackupArchive
        fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "label",
            "backup_type",
            "includes",
            "status",
            "file_name",
            "size_bytes",
            "checksum",
            "last_error",
            "notes",
            "completed_at",
            "restored_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class BackupArchiveCreateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, max_length=48, default="")
    label = serializers.CharField(required=False, allow_blank=True, default="")
    backup_type = serializers.ChoiceField(
        choices=["full", "home", "databases", "email", "custom"],
        default="full",
    )
    includes = serializers.ListField(
        required=False,
        child=serializers.CharField(),
        default=list,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    owner_id = serializers.IntegerField(required=False)


class BackupScheduleSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = BackupSchedule
        fields = (
            "id",
            "owner",
            "owner_username",
            "frequency",
            "includes",
            "hour",
            "weekday",
            "is_active",
            "last_run_at",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "last_run_at",
            "created_at",
            "updated_at",
        )


class BackupScheduleUpsertSerializer(serializers.Serializer):
    frequency = serializers.ChoiceField(
        choices=["daily", "weekly", "monthly"],
        default="weekly",
    )
    includes = serializers.ListField(
        required=False,
        child=serializers.CharField(),
        default=list,
    )
    hour = serializers.IntegerField(required=False, min_value=0, max_value=23, default=2)
    weekday = serializers.IntegerField(required=False, min_value=0, max_value=6, default=0)
    is_active = serializers.BooleanField(required=False, default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    owner_id = serializers.IntegerField(required=False)


class BackupEventLogSerializer(serializers.ModelSerializer):
    archive_name = serializers.CharField(source="archive.name", read_only=True, default="")
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = BackupEventLog
        fields = (
            "id",
            "archive",
            "archive_name",
            "owner",
            "owner_username",
            "event_type",
            "success",
            "message",
            "created_at",
        )
        read_only_fields = fields
