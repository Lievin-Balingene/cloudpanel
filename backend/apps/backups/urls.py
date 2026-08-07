from __future__ import annotations

from django.urls import path

from apps.backups.views import (
    BackupArchiveDetailView,
    BackupArchiveListCreateView,
    BackupDestinationDetailView,
    BackupDestinationListCreateView,
    BackupDownloadView,
    BackupEventLogListView,
    BackupOverviewView,
    BackupRestoreView,
    BackupRetentionView,
    BackupScheduleDetailView,
    BackupScheduleView,
)

urlpatterns = [
    path("overview/", BackupOverviewView.as_view(), name="backup-overview"),
    path("destinations/", BackupDestinationListCreateView.as_view(), name="backup-destination-list"),
    path(
        "destinations/<int:pk>/",
        BackupDestinationDetailView.as_view(),
        name="backup-destination-detail",
    ),
    path("archives/", BackupArchiveListCreateView.as_view(), name="backup-archive-list"),
    path("archives/<int:pk>/", BackupArchiveDetailView.as_view(), name="backup-archive-detail"),
    path("archives/<int:pk>/restore/", BackupRestoreView.as_view(), name="backup-archive-restore"),
    path("archives/<int:pk>/download/", BackupDownloadView.as_view(), name="backup-archive-download"),
    path("schedules/", BackupScheduleView.as_view(), name="backup-schedule-list"),
    path("schedules/<int:pk>/", BackupScheduleDetailView.as_view(), name="backup-schedule-detail"),
    path("retention/", BackupRetentionView.as_view(), name="backup-retention"),
    path("events/", BackupEventLogListView.as_view(), name="backup-event-list"),
]
