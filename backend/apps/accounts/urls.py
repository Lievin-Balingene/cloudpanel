"""Routes d'authentification et de gestion des utilisateurs."""
from __future__ import annotations

from django.urls import path

from apps.accounts.views import (
    AccountLogsListView,
    AccountLogsTailView,
    ChangePasswordView,
    LoginAsView,
    LoginView,
    LogoutView,
    MeView,
    RefreshTokenView,
    ResellerPrivilegeCatalogView,
    ResellerPrivilegesDetailView,
    ResetPasswordView,
    SsoExchangeView,
    SuspendUserView,
    TwoFactorSetupView,
    UserDetailView,
    UserListCreateView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("refresh/", RefreshTokenView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("password/", ChangePasswordView.as_view(), name="auth-password"),
    path("2fa/", TwoFactorSetupView.as_view(), name="auth-2fa"),
    path("sso/exchange/", SsoExchangeView.as_view(), name="auth-sso-exchange"),
    path("users/", UserListCreateView.as_view(), name="user-list"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("users/<int:pk>/suspend/", SuspendUserView.as_view(), name="user-suspend"),
    path("users/<int:pk>/login-as/", LoginAsView.as_view(), name="user-login-as"),
    path(
        "users/<int:pk>/reset-password/",
        ResetPasswordView.as_view(),
        name="user-reset-password",
    ),
    path("users/<int:pk>/logs/", AccountLogsListView.as_view(), name="user-logs-list"),
    path("users/<int:pk>/logs/tail/", AccountLogsTailView.as_view(), name="user-logs-tail"),
    path(
        "reseller-privileges/catalog/",
        ResellerPrivilegeCatalogView.as_view(),
        name="reseller-priv-catalog",
    ),
    path(
        "reseller-privileges/<int:pk>/",
        ResellerPrivilegesDetailView.as_view(),
        name="reseller-priv-detail",
    ),
]
