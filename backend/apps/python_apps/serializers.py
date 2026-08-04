from __future__ import annotations

from rest_framework import serializers

from apps.python_apps.models import PythonApp
from apps.python_apps.services import deploy_info


class PythonAppSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    absolute_root = serializers.SerializerMethodField()
    enter_command = serializers.SerializerMethodField()
    deploy_command = serializers.SerializerMethodField()
    django_project = serializers.SerializerMethodField()

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
            "absolute_root",
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
            "enter_command",
            "deploy_command",
            "django_project",
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
            "absolute_root",
            "port",
            "venv_path",
            "status",
            "pid",
            "last_error",
            "enter_command",
            "deploy_command",
            "django_project",
            "last_started_at",
            "created_at",
            "updated_at",
        )

    def _info(self, obj: PythonApp) -> dict:
        cache = self.context.setdefault("_deploy_info_cache", {})
        key = obj.pk or id(obj)
        if key not in cache:
            try:
                cache[key] = deploy_info(obj)
            except Exception:  # noqa: BLE001
                cache[key] = {
                    "absolute_root": "",
                    "enter_command": "",
                    "deploy_command": "",
                    "django_project": "",
                }
        return cache[key]

    def get_absolute_root(self, obj: PythonApp) -> str:
        return str(self._info(obj).get("absolute_root") or "")

    def get_enter_command(self, obj: PythonApp) -> str:
        return str(self._info(obj).get("enter_command") or "")

    def get_deploy_command(self, obj: PythonApp) -> str:
        return str(self._info(obj).get("deploy_command") or "")

    def get_django_project(self, obj: PythonApp) -> str:
        return str(self._info(obj).get("django_project") or "")


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
