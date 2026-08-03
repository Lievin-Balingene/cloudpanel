from __future__ import annotations

from rest_framework import serializers

from apps.node_apps.models import NodeApp


class NodeAppSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = NodeApp
        fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "label",
            "node_version",
            "framework",
            "relative_root",
            "start_script",
            "entrypoint",
            "port",
            "env_vars",
            "status",
            "pid",
            "last_error",
            "is_active",
            "domain_name",
            "notes",
            "last_started_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "relative_root",
            "port",
            "status",
            "pid",
            "last_error",
            "last_started_at",
            "created_at",
            "updated_at",
        )


class NodeAppCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=48)
    label = serializers.CharField(required=False, allow_blank=True, default="")
    node_version = serializers.CharField(required=False, default="20")
    framework = serializers.ChoiceField(
        choices=["generic", "express", "nest", "next"],
        default="generic",
    )
    relative_root = serializers.CharField(required=False, allow_blank=True, default="")
    start_script = serializers.CharField(required=False, default="start")
    entrypoint = serializers.CharField(required=False, default="server.js")
    domain_name = serializers.CharField(required=False, allow_blank=True, default="")
    env_vars = serializers.DictField(required=False, child=serializers.CharField(), default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    owner_id = serializers.IntegerField(required=False)


class NodeAppUpdateSerializer(serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True)
    start_script = serializers.CharField(required=False, allow_blank=True)
    entrypoint = serializers.CharField(required=False, allow_blank=True)
    domain_name = serializers.CharField(required=False, allow_blank=True)
    env_vars = serializers.DictField(required=False, child=serializers.CharField())
    notes = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
