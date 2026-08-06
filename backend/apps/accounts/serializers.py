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
    primary_domain = serializers.SerializerMethodField()

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
            "primary_domain",
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
            "primary_domain",
            "two_factor_enabled",
        )

    def get_primary_domain(self, obj: User) -> str:
        try:
            from apps.domains.models import Domain

            primary = (
                Domain.objects.filter(
                    owner=obj,
                    domain_type=Domain.DomainType.PRIMARY,
                    is_active=True,
                )
                .order_by("created_at")
                .values_list("name", flat=True)
                .first()
            )
            return primary or ""
        except Exception:  # noqa: BLE001
            return ""


class UserUpdateSerializer(serializers.ModelSerializer):
    """Modification compte (username figé — lié au home cPanel)."""

    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=10
    )
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
            "is_active",
            "is_suspended",
            "must_change_password",
            "module_permissions",
            "parent",
            "quota",
        )
        read_only_fields = ("username",)

    def validate_password(self, value: str) -> str:
        if not value:
            return value
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
                "Un revendeur ne peut assigner que le rôle client."
            )
        return value

    def update(self, instance: User, validated_data: dict) -> User:
        quota_data = validated_data.pop("quota", None)
        password = validated_data.pop("password", None) or None
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
            instance.must_change_password = False
        # Cohérence suspension
        if instance.is_suspended:
            instance.is_active = False
        instance.save()
        if quota_data is not None and hasattr(instance, "quota"):
            for key, value in quota_data.items():
                setattr(instance.quota, key, value)
            instance.quota.save()
        return instance


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=10)
    quota = ResourceQuotaSerializer(required=False)
    # Domaine principal cPanel (obligatoire pour client/revendeur)
    domain = serializers.CharField(required=False, allow_blank=True, default="")
    package_id = serializers.IntegerField(required=False, allow_null=True)
    create_welcome_index = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Si true, écrit index.html « Site prêt » dans public_html.",
    )

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
            "domain",
            "package_id",
            "create_welcome_index",
        )

    def validate_username(self, value: str) -> str:
        from apps.accounts.services import validate_system_username

        try:
            return validate_system_username(value)
        except VZoneAPIException as exc:
            raise serializers.ValidationError(str(exc.detail)) from exc

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

    def validate_domain(self, value: str) -> str:
        name = (value or "").strip().lower().rstrip(".")
        if not name:
            return ""
        if "." not in name or " " in name:
            raise serializers.ValidationError(
                "Domaine principal invalide (FQDN requis, ex: exemple.com)."
            )
        return name

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

    def validate(self, attrs: dict) -> dict:
        role = attrs.get("role") or User.Role.CLIENT
        domain = (attrs.get("domain") or "").strip()
        if role in {User.Role.CLIENT, User.Role.RESELLER} and not domain:
            raise serializers.ValidationError(
                {
                    "domain": "Le domaine principal est requis (comme sur cPanel Create a New Account).",
                }
            )
        return attrs

    def create(self, validated_data: dict) -> User:
        from apps.accounts.services import (
            provision_account_home,
            provision_primary_domain_for_account,
        )

        quota_data = validated_data.pop("quota", None)
        password = validated_data.pop("password")
        domain_name = (validated_data.pop("domain", None) or "").strip()
        package_id = validated_data.pop("package_id", None)
        create_welcome_index = bool(validated_data.pop("create_welcome_index", False))

        user = User.objects.create_user(password=password, **validated_data)
        if quota_data:
            for key, value in quota_data.items():
                setattr(user.quota, key, value)
            user.quota.save()

        provision_account_home(user)
        user.refresh_from_db()

        # Package avant domaine pour appliquer les quotas (domains, disk, …)
        if package_id:
            try:
                from apps.packages.models import HostingPackage
                from apps.packages.services import apply_package_to_user

                package = HostingPackage.objects.get(pk=package_id)
                request = self.context.get("request")
                apply_package_to_user(
                    user,
                    package,
                    assigned_by=getattr(request, "user", None),
                )
            except Exception as exc:  # noqa: BLE001
                raise serializers.ValidationError(
                    {"package_id": f"Impossible d'assigner le package : {exc}"}
                ) from exc

        if domain_name and user.role in {User.Role.CLIENT, User.Role.RESELLER}:
            try:
                provision_primary_domain_for_account(
                    user,
                    domain_name,
                    create_welcome_index=create_welcome_index,
                )
            except VZoneAPIException as exc:
                # Compte créé mais domaine KO — remonter clairement
                raise serializers.ValidationError({"domain": str(exc.detail)}) from exc

        user.refresh_from_db()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField(help_text="E-mail ou nom d'utilisateur")
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict) -> dict:
        from apps.security.services import (
            assert_ip_allowed,
            assert_not_locked,
            client_ip,
            record_login_attempt,
        )

        identifier = attrs["email"].strip()
        password = attrs["password"]
        request = self.context.get("request")
        ip = client_ip(request) if request else None

        user_obj = None
        try:
            if "@" in identifier:
                user_obj = User.objects.get(email__iexact=identifier)
            else:
                user_obj = User.objects.get(username__iexact=identifier)
        except User.DoesNotExist:
            user_obj = None

        lock_key = (user_obj.email if user_obj else identifier).lower()
        assert_ip_allowed(ip)
        assert_not_locked(email=lock_key, ip=ip)

        user = None
        if user_obj is not None:
            user = authenticate(
                request=request,
                username=user_obj.email,
                password=password,
            )
            if user is None and user_obj.check_password(password):
                user = user_obj

        if user is None:
            record_login_attempt(email=lock_key, ip=ip, success=False, message="invalid")
            raise VZoneAPIException(
                detail="Identifiants invalides.",
                code="invalid_credentials",
                status_code=401,
            )

        email = user.email.lower()

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
