from __future__ import annotations

from rest_framework import serializers

from apps.databases.models import Database, DatabasePrivilege, DatabaseUser


class DatabaseSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    privilege_count = serializers.SerializerMethodField()

    class Meta:
        model = Database
        fields = (
            "id",
            "owner",
            "owner_username",
            "engine",
            "name",
            "charset",
            "collation",
            "is_active",
            "notes",
            "size_mb",
            "privilege_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "privilege_count",
            "size_mb",
            "created_at",
            "updated_at",
        )

    def get_privilege_count(self, obj: Database) -> int:
        return obj.privileges.count()


class DatabaseCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=48)
    engine = serializers.ChoiceField(choices=["mysql", "postgresql"], default="mysql")
    charset = serializers.CharField(required=False, default="utf8mb4")
    collation = serializers.CharField(required=False, default="utf8mb4_unicode_ci")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    owner_id = serializers.IntegerField(required=False)


class DatabaseUserSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    privilege_count = serializers.SerializerMethodField()

    class Meta:
        model = DatabaseUser
        fields = (
            "id",
            "owner",
            "owner_username",
            "engine",
            "username",
            "host",
            "is_active",
            "notes",
            "privilege_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "username",
            "privilege_count",
            "created_at",
            "updated_at",
        )

    def get_privilege_count(self, obj: DatabaseUser) -> int:
        return obj.privileges.count()


class DatabaseUserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=32)
    password = serializers.CharField(min_length=8, write_only=True)
    engine = serializers.ChoiceField(choices=["mysql", "postgresql"], default="mysql")
    host = serializers.CharField(required=False, default="localhost")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    owner_id = serializers.IntegerField(required=False)


class DatabaseUserUpdateSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=8, required=False, write_only=True)
    is_active = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class DatabasePrivilegeSerializer(serializers.ModelSerializer):
    database_name = serializers.CharField(source="database.name", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    engine = serializers.CharField(source="database.engine", read_only=True)

    class Meta:
        model = DatabasePrivilege
        fields = (
            "id",
            "database",
            "database_name",
            "user",
            "username",
            "engine",
            "privileges",
            "created_at",
        )
        read_only_fields = fields


class DatabasePrivilegeCreateSerializer(serializers.Serializer):
    database_id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    privileges = serializers.ChoiceField(choices=["ALL", "READ", "WRITE"], default="ALL")
