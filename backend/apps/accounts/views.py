"""Vues API authentification et gestion des utilisateurs."""
from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.models import User
from apps.accounts.permissions import CanManageUsers
from apps.accounts.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    MeSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from apps.accounts.services import issue_tokens, provisioning_uri, revoke_refresh_token
from apps.core.permissions import IsAdministrator


class AuthRateThrottle(AnonRateThrottle):
    scope = "auth"


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [AuthRateThrottle]

    @extend_schema(request=LoginSerializer, responses={200: dict})
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.last_login = timezone.now()
        tokens = issue_tokens(user, request=request)
        return Response(
            {
                "success": True,
                "data": {
                    "tokens": tokens,
                    "user": MeSerializer(user).data,
                },
            }
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"success": False, "error": {"code": "missing_token", "message": "Refresh token requis."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            revoke_refresh_token(refresh, user=request.user)
        except Exception:  # noqa: BLE001
            return Response(
                {"success": False, "error": {"code": "invalid_token", "message": "Token invalide."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"success": True, "data": {"detail": "Déconnecté."}})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": MeSerializer(request.user).data})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        return Response({"success": True, "data": {"detail": "Mot de passe mis à jour."}})


class TwoFactorSetupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        uri = provisioning_uri(request.user)
        return Response(
            {
                "success": True,
                "data": {
                    "otpauth_uri": uri,
                    "secret": request.user.two_factor_secret,
                    "two_factor_enabled": request.user.two_factor_enabled,
                },
            }
        )

    def post(self, request: Request) -> Response:
        from apps.accounts.services import verify_totp

        otp = request.data.get("otp", "")
        if not verify_totp(request.user, otp):
            return Response(
                {
                    "success": False,
                    "error": {"code": "invalid_otp", "message": "Code 2FA invalide."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.two_factor_enabled = True
        request.user.save(update_fields=["two_factor_enabled"])
        return Response({"success": True, "data": {"two_factor_enabled": True}})

    def delete(self, request: Request) -> Response:
        from apps.accounts.services import verify_totp

        otp = request.data.get("otp", "")
        if not request.user.two_factor_enabled:
            return Response({"success": True, "data": {"two_factor_enabled": False}})
        if not verify_totp(request.user, otp):
            return Response(
                {
                    "success": False,
                    "error": {"code": "invalid_otp", "message": "Code 2FA invalide."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.two_factor_enabled = False
        request.user.two_factor_secret = ""
        request.user.save(update_fields=["two_factor_enabled", "two_factor_secret"])
        return Response({"success": True, "data": {"two_factor_enabled": False}})


class UserListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, CanManageUsers]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return UserCreateSerializer
        return UserSerializer

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.select_related("quota", "parent")
        if user.role == User.Role.ADMINISTRATOR:
            return qs
        if user.role == User.Role.RESELLER:
            return qs.filter(parent=user)
        return qs.none()

    def list(self, request: Request, *args, **kwargs) -> Response:
        response = super().list(request, *args, **kwargs)
        if isinstance(response.data, dict) and "results" in response.data:
            return response
        return Response({"success": True, "data": response.data})

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if request.user.role == User.Role.RESELLER:
            serializer.validated_data["parent"] = request.user
        user = serializer.save()
        return Response(
            {"success": True, "data": UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, CanManageUsers]
    lookup_field = "pk"

    def get_serializer_class(self):
        if self.request.method in {"PUT", "PATCH"}:
            return UserUpdateSerializer
        return UserSerializer

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.select_related("quota", "parent")
        if user.role == User.Role.ADMINISTRATOR:
            return qs
        if user.role == User.Role.RESELLER:
            return qs.filter(parent=user)
        return qs.none()

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        return Response({"success": True, "data": UserSerializer(instance).data})

    def update(self, request: Request, *args, **kwargs) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        if instance.role == User.Role.ADMINISTRATOR and not request.user.is_administrator:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "forbidden",
                        "message": "Impossible de modifier un administrateur.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({"success": True, "data": UserSerializer(user).data})

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        from apps.accounts.services import delete_account

        instance = self.get_object()
        if instance.pk == request.user.pk:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "forbidden",
                        "message": "Impossible de supprimer votre propre compte.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if instance.role == User.Role.ADMINISTRATOR and not IsAdministrator().has_permission(
            request, self
        ):
            return Response(status=status.HTTP_403_FORBIDDEN)
        delete_account(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SuspendUserView(APIView):
    permission_classes = [IsAuthenticated, CanManageUsers]

    def post(self, request: Request, pk: int) -> Response:
        try:
            target = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if request.user.role == User.Role.RESELLER and target.parent_id != request.user.pk:
            return Response(status=status.HTTP_403_FORBIDDEN)
        if target.pk == request.user.pk:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "forbidden",
                        "message": "Impossible de suspendre votre propre compte.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        suspended = request.data.get("suspended", True)
        if isinstance(suspended, str):
            suspended = suspended.lower() in {"1", "true", "yes"}
        target.is_suspended = bool(suspended)
        target.is_active = not bool(suspended)
        target.save(update_fields=["is_suspended", "is_active", "updated_at"])
        # Tous les domaines du compte → page suspension (ou site normal si unsuspend)
        try:
            from apps.domains.vhosts import sync_owner_domain_vhosts

            sync_owner_domain_vhosts(target)
        except Exception:  # noqa: BLE001
            pass
        return Response({"success": True, "data": UserSerializer(target).data})


class RefreshTokenView(TokenRefreshView):
    """Rafraîchissement JWT standard encapsulé."""

    def post(self, request: Request, *args, **kwargs) -> Response:
        response = super().post(request, *args, **kwargs)
        return Response({"success": True, "data": response.data}, status=response.status_code)
