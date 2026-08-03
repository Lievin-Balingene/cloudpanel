"""Sérialiseurs d'authentification et de gestion des utilisateurs."""
from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import ResourceQuota, User
from apps.core.exceptions import VZoneAPIException


class ResourceQuotaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceQuota
        fields = (
            "disk_mb",
            "cpu_millicores",
            "ram_mb",
            "emails",
            "databases",
            "domains",
            "ftp_accounts",
            "python_apps",
            "node_apps",
            "docker_containers",
            "unlimited_disk",
            "unlimited_cpu",
            "unlimited_ram",
        )


class UserSerializer(serializers.ModelSerializer):
    quota = ResourceQuotaSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "is_suspended",
            "must_change_password",
            "two_factor_enabled",
            "module_permissions",
            "parent",
            "system_username",
            "home_directory",
            "last_login",
            "last_login_ip",
            "date_joined",
            "quota",
        )
        read_only_fields = (
            "id",
            "last_login",
            "last_login_ip",
            "date_joined",
            "system_username",
            "home_directory",
            "two_factor_enabled",
        )


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=10)
    quota = ResourceQuotaSerializer(required=False)

    class Meta:
        model = User
        fields = (
            "email",
            "username",
            "password",
            "first_name",
            "last_name",
            "role",
            "module_permissions",
            "parent",
            "quota",
        )

    def validate_password(self, value: str) -> str:
        validate_password(value)
        try:
            from apps.security.services import validate_password_against_policy

            validate_password_against_policy(value)
        except ImportError:
            pass
        except VZoneAPIException as exc:
            raise serializers.ValidationError(str(exc.detail)) from exc
        return value

    def validate_role(self, value: str) -> str:
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if actor is None or not actor.is_authenticated:
            raise serializers.ValidationError("Authentification requise.")
        if actor.role == User.Role.RESELLER and value != User.Role.CLIENT:
            raise serializers.ValidationError(
                "Un revendeur ne peut créer que des clients."
            )
        if actor.role == User.Role.CLIENT:
            raise serializers.ValidationError("Un client ne peut pas créer d'utilisateurs.")
        return value

    def create(self, validated_data: dict) -> User:
        quota_data = validated_data.pop("quota", None)
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        if quota_data:
            for key, value in quota_data.items():
                setattr(user.quota, key, value)
            user.quota.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict) -> dict:
        from apps.security.services import (
            assert_ip_allowed,
            assert_not_locked,
            client_ip,
            record_login_attempt,
        )

        email = attrs["email"].lower()
        password = attrs["password"]
        request = self.context.get("request")
        ip = client_ip(request) if request else None

        assert_ip_allowed(ip)
        assert_not_locked(email=email, ip=ip)

        user = authenticate(
            request=request,
            username=email,
            password=password,
        )
        if user is None:
            try:
                candidate = User.objects.get(email__iexact=email)
            except User.DoesNotExist:
                record_login_attempt(email=email, ip=ip, success=False, message="unknown user")
                raise VZoneAPIException(
                    detail="Identifiants invalides.",
                    code="invalid_credentials",
                    status_code=401,
                ) from None
            if not candidate.check_password(password):
                record_login_attempt(email=email, ip=ip, success=False, message="bad password")
                raise VZoneAPIException(
                    detail="Identifiants invalides.",
                    code="invalid_credentials",
                    status_code=401,
                )
            user = candidate

        if not user.is_active or user.is_suspended:
            record_login_attempt(email=email, ip=ip, success=False, message="suspended")
            raise VZoneAPIException(
                detail="Compte désactivé ou suspendu.",
                code="account_disabled",
                status_code=403,
            )

        if user.two_factor_enabled:
            from apps.accounts.services import verify_totp

            otp = attrs.get("otp") or ""
            if not otp:
                raise VZoneAPIException(
                    detail="Code 2FA requis.",
                    code="requires_2fa",
                    status_code=401,
                    extra={"requires_2fa": True},
                )
            if not verify_totp(user, otp):
                record_login_attempt(email=email, ip=ip, success=False, message="bad otp")
                raise VZoneAPIException(
                    detail="Code 2FA invalide.",
                    code="invalid_otp",
                    status_code=401,
                    extra={"requires_2fa": True},
                )

        record_login_attempt(email=email, ip=ip, success=True, message="ok")
        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=10)

    def validate_new_password(self, value: str) -> str:
        validate_password(value, user=self.context["request"].user)
        try:
            from apps.security.services import validate_password_against_policy

            validate_password_against_policy(value)
        except ImportError:
            pass
        return value

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError(
                {"current_password": "Mot de passe actuel incorrect."}
            )
        return attrs


class MeSerializer(UserSerializer):
    """Profil de l'utilisateur connecté."""

    pass
