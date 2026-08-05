from __future__ import annotations

from django.urls import path

from apps.server_setup.views import (
    PanelUpdateJobView,
    PanelUpdateOverviewView,
    PanelUpdateStartView,
    ServerSetupView,
)

urlpatterns = [
    path("", ServerSetupView.as_view(), name="server-setup"),
    path("panel-update/", PanelUpdateOverviewView.as_view(), name="panel-update-overview"),
    path("panel-update/start/", PanelUpdateStartView.as_view(), name="panel-update-start"),
    path("panel-update/jobs/<str:job_id>/", PanelUpdateJobView.as_view(), name="panel-update-job"),
]
