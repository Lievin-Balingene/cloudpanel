from __future__ import annotations

from rest_framework import serializers

from apps.security.models import AccountLockout, IpAccessRule, LoginAttempt, SecurityPolicy


class SecurityPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurityPolicy
        fields = (
            "id",
            "password_min_length",
            "require_uppercase",
            "require_digit",
            "require_special",
            "lockout_max_attempts",
            "lockout_window_minutes",
            "lockout_duration_minutes",
            "ip_mode",
            "force_2fa_admins",
            "updated_at",
        )
        read_only_fields = ("id", "updated_at")


class SecurityPolicyUpdateSerializer(serializers.Serializer):
    password_min_length = serializers.IntegerField(required=False, min_value=6, max_value=128)
    require_uppercase = serializers.BooleanField(required=False)
    require_digit = serializers.BooleanField(required=False)
    require_special = serializers.BooleanField(required=False)
    lockout_max_attempts = serializers.IntegerField(required=False, min_value=1, max_value=50)
    lockout_window_minutes = serializers.IntegerField(required=False, min_value=1, max_value=1440)
    lockout_duration_minutes = serializers.IntegerField(required=False, min_value=1, max_value=10080)
    ip_mode = serializers.ChoiceField(
        choices=["off", "allowlist", "blocklist"],
        required=False,
    )
    force_2fa_admins = serializers.BooleanField(required=False)


class IpAccessRuleSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
        default="",
    )

    class Meta:
        model = IpAccessRule
        fields = (
            "id",
            "cidr",
            "list_type",
            "is_active",
            "notes",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        )


class IpAccessRuleCreateSerializer(serializers.Serializer):
    cidr = serializers.CharField(max_length=64)
    list_type = serializers.ChoiceField(choices=["allow", "block"])
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)


class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = ("id", "email", "ip_address", "success", "message", "created_at")
        read_only_fields = fields


class AccountLockoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountLockout
        fields = ("id", "key", "attempts", "locked_until", "updated_at")
        read_only_fields = fields
