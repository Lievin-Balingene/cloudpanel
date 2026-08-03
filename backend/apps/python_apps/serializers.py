from __future__ import annotations

from rest_framework import serializers

from apps.python_apps.models import PythonApp


class PythonAppSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = PythonApp
        fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "label",
            "python_version",
            "mode",
            "framework",
            "relative_root",
            "entrypoint",
            "port",
            "env_vars",
            "requirements_file",
            "venv_path",
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
            "venv_path",
            "status",
            "pid",
            "last_error",
            "last_started_at",
            "created_at",
            "updated_at",
        )


class PythonAppCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=48)
    label = serializers.CharField(required=False, allow_blank=True, default="")
    python_version = serializers.CharField(required=False, default="3.12")
    mode = serializers.ChoiceField(choices=["wsgi", "asgi"], default="wsgi")
    framework = serializers.ChoiceField(
        choices=["generic", "django", "flask", "fastapi"],
        default="generic",
    )
    relative_root = serializers.CharField(required=False, allow_blank=True, default="")
    entrypoint = serializers.CharField(required=False, allow_blank=True, default="")
    domain_name = serializers.CharField(required=False, allow_blank=True, default="")
    env_vars = serializers.DictField(required=False, child=serializers.CharField(), default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    owner_id = serializers.IntegerField(required=False)


class PythonAppUpdateSerializer(serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True)
    entrypoint = serializers.CharField(required=False, allow_blank=True)
    domain_name = serializers.CharField(required=False, allow_blank=True)
    env_vars = serializers.DictField(required=False, child=serializers.CharField())
    notes = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
