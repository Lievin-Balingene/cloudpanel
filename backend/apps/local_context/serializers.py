"""Sérialiseurs contexte local (exploitation du panneau)."""
from __future__ import annotations

from rest_framework import serializers

from apps.local_context.models import LocalSiteProfile


class LocalSiteProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalSiteProfile
        fields = (
            "country",
            "timezone",
            "data_saver",
            "lite_panel",
            "require_phone",
            "phone_prefix",
            "notify_channel",
            "backup_window_start",
            "backup_window_end",
            "defer_heavy_jobs",
        )

    def validate_backup_window_start(self, value: int) -> int:
        if value > 23:
            raise serializers.ValidationError("Heure entre 0 et 23.")
        return value

    def validate_backup_window_end(self, value: int) -> int:
        if value > 23:
            raise serializers.ValidationError("Heure entre 0 et 23.")
        return value
