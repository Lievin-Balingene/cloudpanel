"""Sérialiseurs OpenAPI pour le module core."""
from __future__ import annotations

from rest_framework import serializers


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()
    version = serializers.CharField()
    timestamp = serializers.CharField()
    checks = serializers.DictField()


class VersionSerializer(serializers.Serializer):
    version = serializers.CharField()
    product = serializers.CharField()
    api = serializers.CharField()


class ModuleSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()
    version = serializers.CharField()
    description = serializers.CharField()
    enabled = serializers.BooleanField()
    dependencies = serializers.ListField(child=serializers.CharField())
