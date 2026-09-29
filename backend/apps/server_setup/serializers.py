from __future__ import annotations

from rest_framework import serializers


class ServerSetupSerializer(serializers.Serializer):
    hostname = serializers.CharField(required=False, allow_blank=True, max_length=255)
    nameserver1 = serializers.CharField(required=False, allow_blank=True, max_length=255)
    nameserver2 = serializers.CharField(required=False, allow_blank=True, max_length=255)
    nameserver3 = serializers.CharField(required=False, allow_blank=True, max_length=255)
    nameserver4 = serializers.CharField(required=False, allow_blank=True, max_length=255)
    resolver1 = serializers.IPAddressField(required=False, allow_null=True)
    resolver2 = serializers.IPAddressField(required=False, allow_null=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    apply_hostname_to_mail = serializers.BooleanField(required=False)
    apply_hostname = serializers.BooleanField(required=False, default=False)


class TweakSettingsUpdateSerializer(serializers.Serializer):
    values = serializers.DictField(child=serializers.JSONField(), required=True)


class ExtraIpSerializer(serializers.Serializer):
    ip = serializers.IPAddressField()


class ChangeSiteIpSerializer(serializers.Serializer):
    domain_id = serializers.IntegerField(min_value=1)
    ipv4_address = serializers.IPAddressField(protocol="IPv4", required=False, allow_null=True)
