from __future__ import annotations

from rest_framework import serializers

from apps.php.models import PhpSelector, PhpVersion


class PhpVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PhpVersion
        fields = (
            "id",
            "version",
            "binary_path",
            "fpm_socket",
            "is_available",
            "is_default",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PhpSelectorSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    php_version_string = serializers.CharField(source="php_version.version", read_only=True)

    class Meta:
        model = PhpSelector
        fields = (
            "id",
            "owner",
            "owner_username",
            "php_version",
            "php_version_string",
            "relative_path",
            "domain_name",
            "handler",
            "ini_settings",
            "extensions",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "php_version_string",
            "relative_path",
            "created_at",
            "updated_at",
        )


class PhpSelectorCreateSerializer(serializers.Serializer):
    php_version_id = serializers.IntegerField()
    relative_path = serializers.CharField(required=False, default="public_html")
    domain_name = serializers.CharField(required=False, allow_blank=True, default="")
    handler = serializers.ChoiceField(choices=["fpm", "cgi", "lsapi"], default="fpm")
    ini_settings = serializers.DictField(required=False, child=serializers.CharField(), default=dict)
    extensions = serializers.ListField(
        required=False,
        child=serializers.CharField(),
        default=list,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    owner_id = serializers.IntegerField(required=False)


class PhpSelectorUpdateSerializer(serializers.Serializer):
    php_version_id = serializers.IntegerField(required=False)
    domain_name = serializers.CharField(required=False, allow_blank=True)
    handler = serializers.ChoiceField(choices=["fpm", "cgi", "lsapi"], required=False)
    ini_settings = serializers.DictField(required=False, child=serializers.CharField())
    extensions = serializers.ListField(required=False, child=serializers.CharField())
    notes = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
