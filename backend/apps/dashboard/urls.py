from __future__ import annotations

from django.urls import path

from apps.dashboard.views import (
    DashboardCaptureView,
    DashboardHistoryView,
    DashboardOverviewView,
    DashboardServerStatusView,
    MetricsVisitorsView,
)

urlpatterns = [
    path("overview/", DashboardOverviewView.as_view(), name="dashboard-overview"),
    path("history/", DashboardHistoryView.as_view(), name="dashboard-history"),
    path("server/", DashboardServerStatusView.as_view(), name="dashboard-server-status"),
    path("metrics/visitors/", MetricsVisitorsView.as_view(), name="dashboard-metrics-visitors"),
    path("capture/", DashboardCaptureView.as_view(), name="dashboard-capture"),
]
