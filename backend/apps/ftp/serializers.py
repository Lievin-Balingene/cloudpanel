from __future__ import annotations

from rest_framework import serializers

from apps.ftp.models import FtpAccount, FtpLog


class FtpAccountSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = FtpAccount
        fields = (
            "id",
            "owner",
            "owner_username",
            "username",
            "directory",
            "relative_directory",
            "quota_mb",
            "bandwidth_kbs",
            "is_active",
            "is_suspended",
            "can_write",
            "notes",
            "status",
            "last_login_at",
            "last_login_ip",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "username",
            "directory",
            "status",
            "last_login_at",
            "last_login_ip",
            "created_at",
            "updated_at",
        )


class FtpAccountCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=64)
    password = serializers.CharField(min_length=8, write_only=True)
    owner_id = serializers.IntegerField(required=False)
    relative_directory = serializers.CharField(required=False, default="public_html")
    quota_mb = serializers.IntegerField(required=False, min_value=0, default=0)
    bandwidth_kbs = serializers.IntegerField(required=False, min_value=0, default=0)
    can_write = serializers.BooleanField(required=False, default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class FtpAccountUpdateSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=8, required=False, write_only=True)
    relative_directory = serializers.CharField(required=False)
    quota_mb = serializers.IntegerField(required=False, min_value=0)
    bandwidth_kbs = serializers.IntegerField(required=False, min_value=0)
    can_write = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class FtpLogSerializer(serializers.ModelSerializer):
    account_username = serializers.CharField(source="account.username", read_only=True, default=None)

    class Meta:
        model = FtpLog
        fields = (
            "id",
            "account",
            "account_username",
            "owner",
            "event_type",
            "username",
            "path",
            "bytes_transferred",
            "ip_address",
            "message",
            "success",
            "created_at",
        )
        read_only_fields = fields


class FtpAuthSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    ip_address = serializers.IPAddressField(required=False, allow_null=True)


class FtpLogCreateSerializer(serializers.Serializer):
    """Permet à un daemon FTP d'injecter des événements."""

    username = serializers.CharField()
    event_type = serializers.ChoiceField(choices=FtpLog.EventType.choices)
    path = serializers.CharField(required=False, allow_blank=True, default="")
    bytes_transferred = serializers.IntegerField(required=False, min_value=0, default=0)
    ip_address = serializers.IPAddressField(required=False, allow_null=True)
    message = serializers.CharField(required=False, allow_blank=True, default="")
    success = serializers.BooleanField(required=False, default=True)
