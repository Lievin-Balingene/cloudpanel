from __future__ import annotations

from rest_framework import serializers


class TransferOptionsSerializer(serializers.Serializer):
    home = serializers.BooleanField(required=False, default=True)
    domains = serializers.BooleanField(required=False, default=True)
    dns = serializers.BooleanField(required=False, default=True)
    databases = serializers.BooleanField(required=False, default=True)
    email = serializers.BooleanField(required=False, default=True)
    ssl = serializers.BooleanField(required=False, default=True)
    ftp = serializers.BooleanField(required=False, default=True)


class ArchiveTransferSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=32)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(required=False, allow_blank=True, default="", max_length=128)
    package_name = serializers.CharField(required=False, allow_blank=True, default="", max_length=64)
    overwrite = serializers.BooleanField(required=False, default=False)
    options = TransferOptionsSerializer(required=False)


class RemoteConnectSerializer(serializers.Serializer):
    host = serializers.CharField(max_length=255)
    port = serializers.IntegerField(required=False, default=2087, min_value=1, max_value=65535)
    user = serializers.CharField(required=False, default="root", max_length=64)
    token = serializers.CharField(max_length=2048)
    insecure_ssl = serializers.BooleanField(required=False, default=False)


class RemoteTransferSerializer(RemoteConnectSerializer):
    remote_username = serializers.CharField(required=False, allow_blank=True, max_length=32, default="")
    username = serializers.CharField(required=False, allow_blank=True, max_length=32, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(required=False, allow_blank=True, default="", max_length=128)
    package_name = serializers.CharField(required=False, allow_blank=True, default="", max_length=64)
    overwrite = serializers.BooleanField(required=False, default=False)
    options = TransferOptionsSerializer(required=False)

    def validate(self, attrs):
        remote = (attrs.get("remote_username") or attrs.get("username") or "").strip()
        if not remote:
            raise serializers.ValidationError(
                {"remote_username": "Sélectionnez ou saisissez le compte cPanel à migrer."}
            )
        attrs["remote_username"] = remote.lower()
        attrs["username"] = remote.lower()
        return attrs


class TransferJobSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    source_type = serializers.CharField()
    status = serializers.CharField()
    username = serializers.CharField()
    email = serializers.EmailField()
    package_name = serializers.CharField()
    overwrite = serializers.BooleanField()
    archive_name = serializers.CharField()
    remote_host = serializers.CharField()
    remote_username = serializers.CharField()
    progress = serializers.IntegerField()
    current_step = serializers.CharField()
    log = serializers.CharField()
    result = serializers.JSONField()
    last_error = serializers.CharField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
