from __future__ import annotations

from rest_framework import serializers

from apps.git_deploy.models import GitDeployLog, GitRepository


class GitRepositorySerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    webhook_path = serializers.SerializerMethodField()

    class Meta:
        model = GitRepository
        fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "label",
            "remote_url",
            "branch",
            "relative_path",
            "deploy_script",
            "auto_deploy",
            "webhook_token",
            "webhook_path",
            "deploy_key_public",
            "last_commit",
            "last_commit_message",
            "status",
            "last_error",
            "last_deploy_at",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "relative_path",
            "webhook_token",
            "webhook_path",
            "deploy_key_public",
            "last_commit",
            "last_commit_message",
            "status",
            "last_error",
            "last_deploy_at",
            "created_at",
            "updated_at",
        )

    def get_webhook_path(self, obj: GitRepository) -> str:
        return f"/api/v1/git/webhook/{obj.webhook_token}/"


class GitRepositoryCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=48)
    remote_url = serializers.CharField(max_length=512)
    branch = serializers.CharField(required=False, default="main")
    relative_path = serializers.CharField(required=False, allow_blank=True, default="")
    deploy_script = serializers.CharField(required=False, allow_blank=True, default="")
    auto_deploy = serializers.BooleanField(required=False, default=True)
    label = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    clone_now = serializers.BooleanField(required=False, default=True)
    owner_id = serializers.IntegerField(required=False)


class GitRepositoryUpdateSerializer(serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True)
    branch = serializers.CharField(required=False)
    deploy_script = serializers.CharField(required=False, allow_blank=True)
    auto_deploy = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class GitDeployLogSerializer(serializers.ModelSerializer):
    repository_name = serializers.CharField(source="repository.name", read_only=True)

    class Meta:
        model = GitDeployLog
        fields = (
            "id",
            "repository",
            "repository_name",
            "event_type",
            "success",
            "message",
            "commit_hash",
            "created_at",
        )
        read_only_fields = fields
