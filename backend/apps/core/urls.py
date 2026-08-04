"""URLs du module core (incluses optionnellement)."""
from __future__ import annotations

from django.urls import path

from apps.core.views import ModuleListView, SystemMetricsView, WebTerminalAccessView

urlpatterns = [
    path("modules/", ModuleListView.as_view(), name="module-list"),
    path("metrics/", SystemMetricsView.as_view(), name="system-metrics"),
    path("terminal/access/", WebTerminalAccessView.as_view(), name="terminal-access"),
]
