from __future__ import annotations

from django.urls import path

from apps.python_apps.views import (
    PythonAppDetailView,
    PythonAppInstallView,
    PythonAppListCreateView,
    PythonAppLogsView,
    PythonAppRestartView,
    PythonAppStartView,
    PythonAppStopView,
    PythonOverviewView,
)

urlpatterns = [
    path("overview/", PythonOverviewView.as_view(), name="python-overview"),
    path("apps/", PythonAppListCreateView.as_view(), name="python-app-list"),
    path("apps/<int:pk>/", PythonAppDetailView.as_view(), name="python-app-detail"),
    path("apps/<int:pk>/start/", PythonAppStartView.as_view(), name="python-app-start"),
    path("apps/<int:pk>/stop/", PythonAppStopView.as_view(), name="python-app-stop"),
    path("apps/<int:pk>/restart/", PythonAppRestartView.as_view(), name="python-app-restart"),
    path("apps/<int:pk>/install/", PythonAppInstallView.as_view(), name="python-app-install"),
    path("apps/<int:pk>/logs/", PythonAppLogsView.as_view(), name="python-app-logs"),
]
