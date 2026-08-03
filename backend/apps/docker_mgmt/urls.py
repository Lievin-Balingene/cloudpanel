from __future__ import annotations

from django.urls import path

from apps.docker_mgmt.views import (
    DockerContainerDetailView,
    DockerContainerListCreateView,
    DockerEventLogListView,
    DockerLogsView,
    DockerOverviewView,
    DockerRestartView,
    DockerStartView,
    DockerStopView,
)

urlpatterns = [
    path("overview/", DockerOverviewView.as_view(), name="docker-overview"),
    path("containers/", DockerContainerListCreateView.as_view(), name="docker-container-list"),
    path("containers/<int:pk>/", DockerContainerDetailView.as_view(), name="docker-container-detail"),
    path("containers/<int:pk>/start/", DockerStartView.as_view(), name="docker-container-start"),
    path("containers/<int:pk>/stop/", DockerStopView.as_view(), name="docker-container-stop"),
    path("containers/<int:pk>/restart/", DockerRestartView.as_view(), name="docker-container-restart"),
    path("containers/<int:pk>/logs/", DockerLogsView.as_view(), name="docker-container-logs"),
    path("events/", DockerEventLogListView.as_view(), name="docker-event-list"),
]
