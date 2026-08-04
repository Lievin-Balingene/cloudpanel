from __future__ import annotations

from django.urls import path

from apps.transfer.views import (
    TransferArchiveInspectView,
    TransferArchiveStartView,
    TransferJobDetailView,
    TransferJobListView,
    TransferRemoteListView,
    TransferRemoteStartView,
)

urlpatterns = [
    path("jobs/", TransferJobListView.as_view(), name="transfer-jobs"),
    path("jobs/<int:pk>/", TransferJobDetailView.as_view(), name="transfer-job-detail"),
    path("archive/inspect/", TransferArchiveInspectView.as_view(), name="transfer-archive-inspect"),
    path("archive/start/", TransferArchiveStartView.as_view(), name="transfer-archive-start"),
    path("remote/list/", TransferRemoteListView.as_view(), name="transfer-remote-list"),
    path("remote/start/", TransferRemoteStartView.as_view(), name="transfer-remote-start"),
]
