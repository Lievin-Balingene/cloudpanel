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
from apps.core.permissions import IsAdministrator, IsResellerOrAdmin


class AuthRateThrottle(AnonRateThrottle):
    scope = "auth"


class ResetPasswordView(APIView):
    """WHM → reset MDP sécurisé (généré serveur, force change, sessions révoquées)."""

    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def post(self, request: Request, pk: int) -> Response:
        from apps.accounts.password_reset import reset_account_password

        target = _managed_user_or_404(request, pk)
        if isinstance(target, Response):
            return target
        confirm = request.data.get("confirm_username") or request.data.get("username") or ""
        data = reset_account_password(
            actor=request.user,
            target=target,
            confirm_username=str(confirm),
            request=request,
        )
        return Response({"success": True, "data": data})


class LoginAsView(APIView):
    """WHM → Login as (cPanel) : jeton SSO one-shot vers le panneau client."""

    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def post(self, request: Request, pk: int) -> Response:
        from apps.accounts.sso import create_login_as_handoff

        if request.user.role == User.Role.RESELLER and not request.user.has_reseller_priv(
            "login-as"
        ):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "reseller_privilege_denied",
                        "message": "Privilege login-as requis.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        qs = User.objects.all()
        if request.user.role == User.Role.RESELLER:
            qs = qs.filter(parent=request.user)
        elif request.user.role != User.Role.ADMINISTRATOR:
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            target = qs.get(pk=pk)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        data = create_login_as_handoff(actor=request.user, target=target, request=request)
        return Response({"success": True, "data": data})


class SsoExchangeView(APIView):
    """Échange le handoff SSO (public, one-shot) contre une session JWT client."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [AuthRateThrottle]

    def post(self, request: Request) -> Response:
        from apps.accounts.sso import consume_login_as_handoff

        token = request.data.get("handoff") or request.data.get("token") or ""
        data = consume_login_as_handoff(str(token))
        return Response({"success": True, "data": data})


def _managed_user_or_404(request: Request, pk: int) -> User | Response:
    qs = User.objects.all()
    if request.user.role == User.Role.RESELLER:
        qs = qs.filter(parent=request.user)
    elif request.user.role != User.Role.ADMINISTRATOR:
        return Response(status=status.HTTP_403_FORBIDDEN)
    try:
        return qs.get(pk=pk)
    except User.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


class AccountLogsListView(APIView):
    """Liste les journaux web (par domaine) d'un compte — WHM Raw Access / Error Log."""

    permission_classes = [IsAuthenticated, CanManageUsers]

    def get(self, request: Request, pk: int) -> Response:
        from apps.accounts.account_logs import list_account_logs, sanitize_logs_for_actor

        target = _managed_user_or_404(request, pk)
        if isinstance(target, Response):
            return target
        data = sanitize_logs_for_actor(list_account_logs(target), request.user)
        return Response({"success": True, "data": data})


class AccountLogsTailView(APIView):
    """Tail d'un journal (domain + kind) pour un compte."""

    permission_classes = [IsAuthenticated, CanManageUsers]

    def get(self, request: Request, pk: int) -> Response:
        from apps.accounts.account_logs import sanitize_log_tail_for_actor, tail_account_log

        target = _managed_user_or_404(request, pk)
        if isinstance(target, Response):
            return target
        domain = (request.query_params.get("domain") or "").strip()
        kind = (request.query_params.get("kind") or "access").strip()
        try:
            lines = int(request.query_params.get("lines") or 200)
        except (TypeError, ValueError):
            lines = 200
        data = sanitize_log_tail_for_actor(
            tail_account_log(target, domain_name=domain, kind=kind, lines=lines),
            request.user,
        )
        return Response({"success": True, "data": data})


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
        try:
            from apps.accounts.password_reset import revoke_all_user_sessions

            revoke_all_user_sessions(user)
        except Exception:  # noqa: BLE001
            pass
        return Response({"success": True, "data": {"detail": "Mot de passe mis à jour."}})


class TwoFactorSetupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        from apps.accounts.services import _totp_plain, provisioning_uri

        uri = provisioning_uri(request.user)
        # Secret en clair uniquement pendant l'enrollment (2FA pas encore active)
        secret = "" if request.user.two_factor_enabled else _totp_plain(request.user)
        return Response(
            {
                "success": True,
                "data": {
                    "otpauth_uri": uri if not request.user.two_factor_enabled else "",
                    "secret": secret,
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
    pagination_class = None  # overriden in list() for scalable paging

    def get_serializer_class(self):
        if self.request.method == "POST":
            return UserCreateSerializer
        return UserSerializer

    def get_queryset(self):
        from django.db.models import OuterRef, Subquery

        from apps.domains.models import Domain

        user = self.request.user
        primary = (
            Domain.objects.filter(
                owner_id=OuterRef("pk"),
                domain_type=Domain.DomainType.PRIMARY,
                is_active=True,
            )
            .order_by("created_at")
            .values("name")[:1]
        )
        qs = (
            User.objects.select_related("quota", "parent", "package_assignment__package")
            .annotate(primary_domain_name=Subquery(primary))
            .order_by("-date_joined", "username")
        )
        if user.role == User.Role.ADMINISTRATOR:
            pass
        elif user.role == User.Role.RESELLER:
            qs = qs.filter(parent=user)
        else:
            return qs.none()

        q = (self.request.query_params.get("q") or "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(primary_domain_name__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )

        role = (self.request.query_params.get("role") or "").strip()
        if role in {User.Role.CLIENT, User.Role.RESELLER, User.Role.ADMINISTRATOR}:
            qs = qs.filter(role=role)

        status_f = (self.request.query_params.get("status") or "").strip().lower()
        if status_f == "suspended":
            qs = qs.filter(is_suspended=True)
        elif status_f == "active":
            qs = qs.filter(is_suspended=False, is_active=True)

        # Filtre propriétaire / revendeur (admin only — un reseller est déjà scopé)
        parent_raw = (self.request.query_params.get("parent") or "").strip().lower()
        if user.role == User.Role.ADMINISTRATOR and parent_raw:
            if parent_raw in {"root", "0", "none"}:
                qs = qs.filter(parent__isnull=True).exclude(role=User.Role.ADMINISTRATOR)
            else:
                try:
                    parent_id = int(parent_raw)
                except ValueError:
                    parent_id = None
                if parent_id is not None:
                    # Comptes du reseller (+ optionnellement le reseller lui-même via include_reseller=1)
                    include_self = (self.request.query_params.get("include_reseller") or "").strip() in {
                        "1",
                        "true",
                        "yes",
                    }
                    if include_self:
                        from django.db.models import Q

                        qs = qs.filter(Q(parent_id=parent_id) | Q(pk=parent_id))
                    else:
                        qs = qs.filter(parent_id=parent_id)

        return qs

    def list(self, request: Request, *args, **kwargs) -> Response:
        from apps.accounts.disk_usage_list import batch_disk_used_mb
        from apps.core.pagination import StandardPagination

        queryset = self.filter_queryset(self.get_queryset())
        paginator = StandardPagination()
        # List Accounts : pages plus larges pour WHM (toujours plafonné)
        paginator.page_size = 50
        paginator.max_page_size = 200
        page = paginator.paginate_queryset(queryset, request, view=self)
        rows = page if page is not None else list(queryset[:200])
        disk_map = batch_disk_used_mb(rows, refresh_missing=True)
        serializer = self.get_serializer(
            rows,
            many=True,
            context={**self.get_serializer_context(), "disk_used_map": disk_map},
        )
        if page is not None:
            return paginator.get_paginated_response(serializer.data)
        return Response({"success": True, "data": serializer.data})

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
        try:
            from apps.server_setup.contact_notify import notify_account_termination

            notify_account_termination(instance, actor=request.user, request=request)
        except Exception:  # noqa: BLE001
            pass
        delete_account(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SuspendUserView(APIView):
    permission_classes = [IsAuthenticated, CanManageUsers]

    def post(self, request: Request, pk: int) -> Response:
        if request.user.role == User.Role.RESELLER and not request.user.has_reseller_priv(
            "suspend-acct"
        ):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "reseller_privilege_denied",
                        "message": "Privilege suspend-acct requis.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        # Même scope que UserDetailView (anti-IDOR : pas de get() global)
        qs = User.objects.all()
        if request.user.role == User.Role.ADMINISTRATOR:
            pass
        elif request.user.role == User.Role.RESELLER:
            qs = qs.filter(parent=request.user)
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            target = qs.get(pk=pk)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

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
        if target.role == User.Role.ADMINISTRATOR and request.user.role != User.Role.ADMINISTRATOR:
            return Response(status=status.HTTP_403_FORBIDDEN)
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
        try:
            from apps.server_setup.contact_notify import notify_account_suspend

            notify_account_suspend(
                target,
                actor=request.user,
                request=request,
                suspended=bool(suspended),
            )
        except Exception:  # noqa: BLE001
            pass
        return Response({"success": True, "data": UserSerializer(target).data})


class RefreshTokenView(TokenRefreshView):
    """Rafraîchissement JWT — refuse si le rôle ne correspond pas au port (Admin/Client)."""

    def post(self, request: Request, *args, **kwargs) -> Response:
        from rest_framework_simplejwt.exceptions import TokenError
        from rest_framework_simplejwt.tokens import RefreshToken

        from apps.accounts.models import User
        from apps.security.portal import assert_role_allowed_on_portal, request_portal

        portal = request_portal(request)
        raw = request.data.get("refresh") or ""
        if raw and portal in {"admin", "client", "webmail"}:
            try:
                token = RefreshToken(raw)
                user = User.objects.get(pk=token.get("user_id"))
            except (TokenError, User.DoesNotExist, KeyError, TypeError, ValueError):
                user = None
            if user is not None:
                assert_role_allowed_on_portal(user, portal)

        response = super().post(request, *args, **kwargs)
        return Response({"success": True, "data": response.data}, status=response.status_code)


class ResellerPrivilegeCatalogView(APIView):
    """Catalogue des privileges (Edit Reseller Privileges)."""

    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def get(self, request: Request) -> Response:
        from apps.accounts.reseller_acl import catalog_as_list

        return Response({"success": True, "data": catalog_as_list()})


class ResellerPrivilegesDetailView(APIView):
    """
    GET/PUT privileges d'un revendeur.
    Admin : tous. Revendeur : lecture de ses propres privileges uniquement.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        from apps.accounts.models import ResellerPrivileges
        from apps.accounts.reseller_acl import catalog_as_list, default_privileges_for_package
        from apps.accounts.reseller_services import ensure_reseller_privileges

        try:
            target = User.objects.get(pk=pk, role=User.Role.RESELLER)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if request.user.is_reseller and request.user.pk != target.pk:
            return Response(status=status.HTTP_403_FORBIDDEN)
        if not (request.user.is_administrator or request.user.is_reseller):
            return Response(status=status.HTTP_403_FORBIDDEN)

        acl = ResellerPrivileges.objects.filter(user=target).first()
        if acl is None:
            acl = ensure_reseller_privileges(target)

        from apps.accounts.reseller_services import resolve_reseller_account_limit

        limits = resolve_reseller_account_limit(target)

        return Response(
            {
                "success": True,
                "data": {
                    "user_id": target.pk,
                    "username": target.username,
                    "privileges": list(acl.privileges or []),
                    "enforce_ownership": acl.enforce_ownership,
                    "allow_overselling": acl.allow_overselling,
                    "max_accounts": acl.max_accounts,
                    "account_limits": limits,
                    "notes": acl.notes,
                    "catalog": catalog_as_list(),
                    "defaults": default_privileges_for_package(),
                },
            }
        )

    def put(self, request: Request, pk: int) -> Response:
        from apps.accounts.reseller_acl import sanitize_privileges
        from apps.accounts.reseller_services import (
            ensure_reseller_privileges,
            resolve_reseller_account_limit,
        )

        if not request.user.is_administrator:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "forbidden",
                        "message": "Seul un administrateur peut modifier les privileges revendeur.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            target = User.objects.get(pk=pk, role=User.Role.RESELLER)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        privileges = sanitize_privileges(request.data.get("privileges") or [])
        acl = ensure_reseller_privileges(
            target,
            privileges=privileges,
            updated_by=request.user,
        )
        if "enforce_ownership" in request.data:
            acl.enforce_ownership = bool(request.data.get("enforce_ownership"))
        if "allow_overselling" in request.data:
            acl.allow_overselling = bool(request.data.get("allow_overselling"))
        if "notes" in request.data:
            acl.notes = str(request.data.get("notes") or "")[:255]
        if "max_accounts" in request.data:
            raw = request.data.get("max_accounts")
            if raw is None or raw == "":
                acl.max_accounts = None
            else:
                try:
                    n = int(raw)
                except (TypeError, ValueError):
                    return Response(
                        {
                            "success": False,
                            "error": {
                                "code": "invalid_max_accounts",
                                "message": "max_accounts doit être un entier (≥ 0) ou null (hériter du package).",
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if n < 0:
                    n = 0
                acl.max_accounts = n
        acl.updated_by = request.user
        acl.save()
        limits = resolve_reseller_account_limit(target)
        return Response(
            {
                "success": True,
                "data": {
                    "user_id": target.pk,
                    "username": target.username,
                    "privileges": list(acl.privileges or []),
                    "enforce_ownership": acl.enforce_ownership,
                    "allow_overselling": acl.allow_overselling,
                    "max_accounts": acl.max_accounts,
                    "account_limits": limits,
                    "notes": acl.notes,
                },
            }
        )
