from __future__ import annotations

from rest_framework import serializers

from apps.docker_mgmt.models import (
    DockerBuildJob,
    DockerComposeProject,
    DockerContainer,
    DockerContainerLog,
)


class DockerContainerSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    image_ref = serializers.CharField(read_only=True)

    class Meta:
        model = DockerContainer
        fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "label",
            "image",
            "tag",
            "image_ref",
            "container_id",
            "status",
            "ports",
            "env_vars",
            "volumes",
            "command",
            "restart_policy",
            "memory_mb",
            "cpus",
            "last_error",
            "is_active",
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
            "image_ref",
            "container_id",
            "status",
            "last_error",
            "last_started_at",
            "created_at",
            "updated_at",
        )


class DockerContainerCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=48)
    image = serializers.CharField(max_length=255)
    tag = serializers.CharField(required=False, default="latest")
    ports = serializers.DictField(required=False, child=serializers.CharField(), default=dict)
    env_vars = serializers.DictField(required=False, child=serializers.CharField(), default=dict)
    volumes = serializers.ListField(required=False, child=serializers.CharField(), default=list)
    command = serializers.CharField(required=False, allow_blank=True, default="")
    restart_policy = serializers.ChoiceField(
        choices=["no", "always", "unless-stopped", "on-failure"],
        default="unless-stopped",
    )
    memory_mb = serializers.IntegerField(required=False, min_value=64, default=512)
    cpus = serializers.DecimalField(required=False, max_digits=4, decimal_places=2, default=1)
    label = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    start_now = serializers.BooleanField(required=False, default=True)
    owner_id = serializers.IntegerField(required=False)


class DockerContainerUpdateSerializer(serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True)
    env_vars = serializers.DictField(required=False, child=serializers.CharField())
    notes = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    memory_mb = serializers.IntegerField(required=False, min_value=64)
    restart_policy = serializers.ChoiceField(
        choices=["no", "always", "unless-stopped", "on-failure"],
        required=False,
    )


class DockerContainerLogSerializer(serializers.ModelSerializer):
    container_name = serializers.CharField(source="container.name", read_only=True)

    class Meta:
        model = DockerContainerLog
        fields = (
            "id",
            "container",
            "container_name",
            "event_type",
            "success",
            "message",
            "created_at",
        )
        read_only_fields = fields


class DockerBuildJobSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = DockerBuildJob
        fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "context_path",
            "dockerfile",
            "image_name",
            "tag",
            "built_image_ref",
            "status",
            "progress",
            "log",
            "last_error",
            "no_cache",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "built_image_ref",
            "status",
            "progress",
            "log",
            "last_error",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )


class DockerBuildCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=48)
    context_path = serializers.CharField(max_length=512)
    dockerfile = serializers.CharField(required=False, default="Dockerfile")
    image_name = serializers.CharField(required=False, allow_blank=True, default="")
    tag = serializers.CharField(required=False, default="latest")
    no_cache = serializers.BooleanField(required=False, default=False)
    owner_id = serializers.IntegerField(required=False)


class DockerComposeProjectSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = DockerComposeProject
        fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "project_path",
            "compose_file",
            "status",
            "log",
            "last_error",
            "last_deployed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DockerComposeCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=48)
    project_path = serializers.CharField(max_length=512)
    compose_file = serializers.CharField(required=False, allow_blank=True, default="")
    owner_id = serializers.IntegerField(required=False)


class DockerImagePullSerializer(serializers.Serializer):
    image = serializers.CharField(max_length=255)
    tag = serializers.CharField(required=False, default="latest")


class DockerImageRemoveSerializer(serializers.Serializer):
    repository = serializers.CharField(max_length=255)
    tag = serializers.CharField(required=False, default="latest")


class DockerDockerfileTemplateSerializer(serializers.Serializer):
    context_path = serializers.CharField(max_length=512)
    kind = serializers.ChoiceField(choices=["node", "nginx", "python"], default="node")
