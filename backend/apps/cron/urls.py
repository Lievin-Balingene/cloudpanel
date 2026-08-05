from __future__ import annotations

from django.urls import path

from apps.cron.views import (
    CronJobDetailView,
    CronJobListCreateView,
    CronOverviewView,
    CronPreviewView,
    CronSyncView,
)

urlpatterns = [
    path("jobs/", CronJobListCreateView.as_view(), name="cron-job-list"),
    path("jobs/<int:pk>/", CronJobDetailView.as_view(), name="cron-job-detail"),
    path("overview/", CronOverviewView.as_view(), name="cron-overview"),
    path("preview/", CronPreviewView.as_view(), name="cron-preview"),
    path("sync/", CronSyncView.as_view(), name="cron-sync"),
]
