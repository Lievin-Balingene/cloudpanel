from __future__ import annotations

from django.urls import path

from apps.node_apps.views import (
    NodeAppDetailView,
    NodeAppInstallView,
    NodeAppListCreateView,
    NodeAppLogsView,
    NodeAppRestartView,
    NodeAppStartView,
    NodeAppStopView,
    NodeOverviewView,
)

urlpatterns = [
    path("overview/", NodeOverviewView.as_view(), name="node-overview"),
    path("apps/", NodeAppListCreateView.as_view(), name="node-app-list"),
    path("apps/<int:pk>/", NodeAppDetailView.as_view(), name="node-app-detail"),
    path("apps/<int:pk>/start/", NodeAppStartView.as_view(), name="node-app-start"),
    path("apps/<int:pk>/stop/", NodeAppStopView.as_view(), name="node-app-stop"),
    path("apps/<int:pk>/restart/", NodeAppRestartView.as_view(), name="node-app-restart"),
    path("apps/<int:pk>/install/", NodeAppInstallView.as_view(), name="node-app-install"),
    path("apps/<int:pk>/logs/", NodeAppLogsView.as_view(), name="node-app-logs"),
]
