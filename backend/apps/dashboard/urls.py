from __future__ import annotations

from django.urls import path

from apps.dashboard.views import (
    DashboardCaptureView,
    DashboardHistoryView,
    DashboardOverviewView,
)

urlpatterns = [
    path("overview/", DashboardOverviewView.as_view(), name="dashboard-overview"),
    path("history/", DashboardHistoryView.as_view(), name="dashboard-history"),
    path("capture/", DashboardCaptureView.as_view(), name="dashboard-capture"),
]
