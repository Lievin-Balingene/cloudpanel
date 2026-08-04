from __future__ import annotations

from rest_framework import serializers


class KubernetesManifestSerializer(serializers.Serializer):
    manifest = serializers.CharField()
    namespace = serializers.CharField(required=False, allow_blank=True, default="")
