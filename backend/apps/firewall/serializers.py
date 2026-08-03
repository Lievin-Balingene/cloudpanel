from __future__ import annotations

from rest_framework import serializers

from apps.firewall.models import Fail2BanBan, Fail2BanJail, FirewallEventLog, FirewallRule


class FirewallRuleSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
        default="",
    )

    class Meta:
        model = FirewallRule
        fields = (
            "id",
            "name",
            "action",
            "protocol",
            "direction",
            "port_start",
            "port_end",
            "source_cidr",
            "dest_cidr",
            "priority",
            "is_enabled",
            "is_applied",
            "notes",
            "last_error",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "is_applied",
            "last_error",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )


class FirewallRuleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    action = serializers.ChoiceField(choices=["allow", "deny"], default="allow")
    protocol = serializers.ChoiceField(choices=["tcp", "udp", "any"], default="tcp")
    direction = serializers.ChoiceField(choices=["in", "out"], default="in")
    port_start = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=65535)
    port_end = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=65535)
    source_cidr = serializers.CharField(required=False, allow_blank=True, default="")
    dest_cidr = serializers.CharField(required=False, allow_blank=True, default="")
    priority = serializers.IntegerField(required=False, min_value=0, default=100)
    is_enabled = serializers.BooleanField(required=False, default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    apply_now = serializers.BooleanField(required=False, default=False)


class FirewallRuleUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=120)
    action = serializers.ChoiceField(choices=["allow", "deny"], required=False)
    protocol = serializers.ChoiceField(choices=["tcp", "udp", "any"], required=False)
    direction = serializers.ChoiceField(choices=["in", "out"], required=False)
    port_start = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=65535)
    port_end = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=65535)
    source_cidr = serializers.CharField(required=False, allow_blank=True)
    dest_cidr = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.IntegerField(required=False, min_value=0)
    is_enabled = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class Fail2BanJailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fail2BanJail
        fields = (
            "id",
            "name",
            "is_enabled",
            "filter_name",
            "max_retry",
            "find_time",
            "ban_time",
            "currently_banned",
            "total_banned",
            "notes",
            "updated_at",
        )
        read_only_fields = fields


class Fail2BanBanSerializer(serializers.ModelSerializer):
    jail_name = serializers.CharField(source="jail.name", read_only=True)
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
        default="",
    )

    class Meta:
        model = Fail2BanBan
        fields = (
            "id",
            "jail",
            "jail_name",
            "ip_address",
            "status",
            "reason",
            "banned_at",
            "unbanned_at",
            "created_by",
            "created_by_username",
        )
        read_only_fields = fields


class BanIpSerializer(serializers.Serializer):
    ip_address = serializers.IPAddressField()
    jail_name = serializers.CharField(required=False, default="sshd")
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class UnbanIpSerializer(serializers.Serializer):
    ip_address = serializers.IPAddressField()
    jail_name = serializers.CharField(required=False, allow_blank=True, default="")


class FirewallEventLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default="")

    class Meta:
        model = FirewallEventLog
        fields = (
            "id",
            "event_type",
            "success",
            "message",
            "actor",
            "actor_username",
            "created_at",
        )
        read_only_fields = fields
