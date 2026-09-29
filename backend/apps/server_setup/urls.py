from __future__ import annotations

from django.urls import path

from apps.server_setup.views import (
    ChangeSiteIpView,
    ExtraIpView,
    IpFunctionsView,
    OlsAdoptView,
    OlsOverviewView,
    OlsReloadView,
    PanelUpdateBootstrapView,
    PanelUpdateJobView,
    PanelUpdateOverviewView,
    PanelUpdateStartView,
    RepairJobView,
    RepairStartView,
    RepairsOverviewView,
    ServerSetupView,
    TweakSettingsView,
)

urlpatterns = [
    path("", ServerSetupView.as_view(), name="server-setup"),
    path("tweak-settings/", TweakSettingsView.as_view(), name="tweak-settings"),
    path("ip-functions/", IpFunctionsView.as_view(), name="ip-functions"),
    path("ip-functions/extra/", ExtraIpView.as_view(), name="ip-functions-extra"),
    path("ip-functions/change-site/", ChangeSiteIpView.as_view(), name="ip-functions-change-site"),
    path("panel-update/", PanelUpdateOverviewView.as_view(), name="panel-update-overview"),
    path(
        "panel-update/bootstrap/",
        PanelUpdateBootstrapView.as_view(),
        name="panel-update-bootstrap",
    ),
    path("panel-update/start/", PanelUpdateStartView.as_view(), name="panel-update-start"),
    path("panel-update/jobs/<str:job_id>/", PanelUpdateJobView.as_view(), name="panel-update-job"),
    path("repairs/", RepairsOverviewView.as_view(), name="repairs-overview"),
    path("repairs/start/", RepairStartView.as_view(), name="repairs-start"),
    path("repairs/jobs/<str:job_id>/", RepairJobView.as_view(), name="repairs-job"),
    path("ols/", OlsOverviewView.as_view(), name="ols-overview"),
    path("ols/reload/", OlsReloadView.as_view(), name="ols-reload"),
    path("ols/adopt/", OlsAdoptView.as_view(), name="ols-adopt"),
]
