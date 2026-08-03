from __future__ import annotations

from django.urls import path

from apps.ftp.views import (
    FtpAccountDetailView,
    FtpAccountListCreateView,
    FtpAuthView,
    FtpLogIngestView,
    FtpLogListView,
    FtpStatsView,
    FtpSuspendView,
)

urlpatterns = [
    path("accounts/", FtpAccountListCreateView.as_view(), name="ftp-account-list"),
    path("accounts/<int:pk>/", FtpAccountDetailView.as_view(), name="ftp-account-detail"),
    path("accounts/<int:pk>/suspend/", FtpSuspendView.as_view(), name="ftp-account-suspend"),
    path("logs/", FtpLogListView.as_view(), name="ftp-log-list"),
    path("stats/", FtpStatsView.as_view(), name="ftp-stats"),
    path("auth/", FtpAuthView.as_view(), name="ftp-auth"),
    path("logs/ingest/", FtpLogIngestView.as_view(), name="ftp-log-ingest"),
]
