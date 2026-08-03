"""Routes d'authentification et de gestion des utilisateurs."""
from __future__ import annotations

from django.urls import path

from apps.accounts.views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshTokenView,
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
    path("users/", UserListCreateView.as_view(), name="user-list"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("users/<int:pk>/suspend/", SuspendUserView.as_view(), name="user-suspend"),
]
