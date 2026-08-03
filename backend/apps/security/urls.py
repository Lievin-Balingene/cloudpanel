from __future__ import annotations

from django.urls import path

from apps.security.views import (
    AccountLockoutListView,
    AccountUnlockView,
    ForcePasswordChangeView,
    IpAccessRuleDetailView,
    IpAccessRuleListCreateView,
    LoginAttemptListView,
    MySecurityStatusView,
    SecurityOverviewView,
    SecurityPolicyView,
)

urlpatterns = [
    path("overview/", SecurityOverviewView.as_view(), name="security-overview"),
    path("policy/", SecurityPolicyView.as_view(), name="security-policy"),
    path("ip-rules/", IpAccessRuleListCreateView.as_view(), name="security-ip-list"),
    path("ip-rules/<int:pk>/", IpAccessRuleDetailView.as_view(), name="security-ip-detail"),
    path("attempts/", LoginAttemptListView.as_view(), name="security-attempts"),
    path("lockouts/", AccountLockoutListView.as_view(), name="security-lockouts"),
    path("unlock/", AccountUnlockView.as_view(), name="security-unlock"),
    path("users/<int:pk>/force-password/", ForcePasswordChangeView.as_view(), name="security-force-password"),
    path("me/", MySecurityStatusView.as_view(), name="security-me"),
]
