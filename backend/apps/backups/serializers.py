from __future__ import annotations

from rest_framework import serializers

from apps.backups.models import BackupArchive, BackupDestination, BackupEventLog, BackupSchedule


class BackupDestinationSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True, default="")

    class Meta:
        model = BackupDestination
        fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "label",
            "provider",
            "config",
            "rclone_remote",
            "repository_uri",
            "is_default",
            "is_active",
            "last_error",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "rclone_remote",
            "repository_uri",
            "last_error",
            "created_at",
            "updated_at",
        )


class BackupDestinationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=48)
    label = serializers.CharField(required=False, allow_blank=True, default="")
    provider = serializers.ChoiceField(
        choices=["local", "sftp", "s3", "b2", "r2", "gdrive"],
        default="local",
    )
    config = serializers.DictField(required=False, default=dict)
    credentials = serializers.DictField(required=False, default=dict)
    restic_password = serializers.CharField(required=False, allow_blank=True, default="")
    is_default = serializers.BooleanField(required=False, default=False)
    owner_id = serializers.IntegerField(required=False)


class BackupArchiveSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    destination_name = serializers.CharField(
        source="destination.name", read_only=True, default=""
    )
    destination_provider = serializers.CharField(
        source="destination.provider", read_only=True, default=""
    )

    class Meta:
        model = BackupArchive
        fields = (
            "id",
            "owner",
            "owner_username",
            "destination",
            "destination_name",
            "destination_provider",
            "name",
            "label",
            "backup_type",
            "trigger",
            "includes",
            "status",
            "snapshot_id",
            "parent_snapshot_id",
            "file_name",
            "size_bytes",
            "files_new",
            "files_changed",
            "files_unmodified",
            "checksum",
            "progress",
            "duration_seconds",
            "log",
            "last_error",
            "notes",
            "celery_task_id",
            "started_at",
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
        choices=["full", "incremental", "home", "databases", "email", "custom"],
        default="full",
    )
    includes = serializers.ListField(
        required=False,
        child=serializers.CharField(),
        default=list,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    owner_id = serializers.IntegerField(required=False)
    destination_id = serializers.IntegerField(required=False)
    async_run = serializers.BooleanField(required=False, default=True)


class BackupScheduleSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    destination_name = serializers.CharField(
        source="destination.name", read_only=True, default=""
    )

    class Meta:
        model = BackupSchedule
        fields = (
            "id",
            "owner",
            "owner_username",
            "destination",
            "destination_name",
            "name",
            "frequency",
            "includes",
            "hour",
            "minute",
            "weekday",
            "keep_hourly",
            "keep_daily",
            "keep_weekly",
            "keep_monthly",
            "is_active",
            "last_run_at",
            "next_run_at",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "destination_name",
            "last_run_at",
            "next_run_at",
            "created_at",
            "updated_at",
        )


class BackupScheduleUpsertSerializer(serializers.Serializer):
    frequency = serializers.ChoiceField(
        choices=["hourly", "daily", "weekly", "monthly"],
        default="weekly",
    )
    includes = serializers.ListField(
        required=False,
        child=serializers.CharField(),
        default=list,
    )
    hour = serializers.IntegerField(required=False, min_value=0, max_value=23, default=2)
    minute = serializers.IntegerField(required=False, min_value=0, max_value=59, default=0)
    weekday = serializers.IntegerField(required=False, min_value=0, max_value=6, default=0)
    is_active = serializers.BooleanField(required=False, default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    name = serializers.CharField(required=False, allow_blank=True, default="")
    owner_id = serializers.IntegerField(required=False)
    destination_id = serializers.IntegerField(required=False)
    keep_hourly = serializers.IntegerField(required=False, min_value=0, default=0)
    keep_daily = serializers.IntegerField(required=False, min_value=0, default=7)
    keep_weekly = serializers.IntegerField(required=False, min_value=0, default=4)
    keep_monthly = serializers.IntegerField(required=False, min_value=0, default=6)


class BackupRetentionSerializer(serializers.Serializer):
    destination_id = serializers.IntegerField()
    owner_id = serializers.IntegerField(required=False)
    keep_hourly = serializers.IntegerField(required=False, min_value=0, default=0)
    keep_daily = serializers.IntegerField(required=False, min_value=0, default=7)
    keep_weekly = serializers.IntegerField(required=False, min_value=0, default=4)
    keep_monthly = serializers.IntegerField(required=False, min_value=0, default=6)


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
