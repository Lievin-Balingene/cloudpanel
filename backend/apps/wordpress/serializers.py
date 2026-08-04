from __future__ import annotations

from rest_framework import serializers

from apps.wordpress.models import WordPressSite


class WordPressSiteSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    domain_name = serializers.CharField(source="domain.name", read_only=True)
    database_name = serializers.SerializerMethodField()
    db_username = serializers.SerializerMethodField()

    class Meta:
        model = WordPressSite
        fields = (
            "id",
            "owner",
            "owner_username",
            "domain",
            "domain_name",
            "title",
            "admin_user",
            "admin_email",
            "document_root",
            "site_url",
            "admin_url",
            "database",
            "database_name",
            "db_user",
            "db_username",
            "php_version",
            "status",
            "last_error",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_database_name(self, obj: WordPressSite) -> str:
        return obj.database.name if obj.database_id else ""

    def get_db_username(self, obj: WordPressSite) -> str:
        return obj.db_user.username if obj.db_user_id else ""


class WordPressInstallSerializer(serializers.Serializer):
    domain_id = serializers.IntegerField()
    title = serializers.CharField(required=False, allow_blank=True, default="Mon site", max_length=200)
    admin_user = serializers.CharField(required=False, allow_blank=True, default="admin", max_length=60)
    admin_email = serializers.EmailField(required=False, allow_blank=True, default="")
    admin_password = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=128,
        write_only=True,
    )
    locale = serializers.CharField(required=False, default="fr_FR", max_length=16)
    owner_id = serializers.IntegerField(required=False)
