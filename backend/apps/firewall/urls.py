from __future__ import annotations

from django.urls import path

from apps.firewall.views import (
    Fail2BanBanListView,
    Fail2BanBanView,
    Fail2BanJailListView,
    Fail2BanSyncView,
    Fail2BanUnbanView,
    FirewallEventLogListView,
    FirewallOverviewView,
    FirewallRuleApplyView,
    FirewallRuleDetailView,
    FirewallRuleListCreateView,
)

urlpatterns = [
    path("overview/", FirewallOverviewView.as_view(), name="firewall-overview"),
    path("rules/", FirewallRuleListCreateView.as_view(), name="firewall-rule-list"),
    path("rules/<int:pk>/", FirewallRuleDetailView.as_view(), name="firewall-rule-detail"),
    path("rules/<int:pk>/apply/", FirewallRuleApplyView.as_view(), name="firewall-rule-apply"),
    path("fail2ban/jails/", Fail2BanJailListView.as_view(), name="firewall-f2b-jails"),
    path("fail2ban/bans/", Fail2BanBanListView.as_view(), name="firewall-f2b-bans"),
    path("fail2ban/ban/", Fail2BanBanView.as_view(), name="firewall-f2b-ban"),
    path("fail2ban/unban/", Fail2BanUnbanView.as_view(), name="firewall-f2b-unban"),
    path("fail2ban/sync/", Fail2BanSyncView.as_view(), name="firewall-f2b-sync"),
    path("events/", FirewallEventLogListView.as_view(), name="firewall-event-list"),
]
