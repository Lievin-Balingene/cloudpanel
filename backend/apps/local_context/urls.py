from __future__ import annotations

from django.urls import path

from apps.local_context.views import (
    LocalNoticeView,
    LocalOverviewView,
    LocalProfileView,
    LocalRecoverView,
)

urlpatterns = [
    path("profile/", LocalProfileView.as_view(), name="local-context-profile"),
    path("overview/", LocalOverviewView.as_view(), name="local-context-overview"),
    path("recover/", LocalRecoverView.as_view(), name="local-context-recover"),
    path("notice/", LocalNoticeView.as_view(), name="local-context-notice"),
]
