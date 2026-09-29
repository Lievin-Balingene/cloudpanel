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
from apps.docker_mgmt.views_build import (
    DockerBuildDetailView,
    DockerBuildListCreateView,
    DockerComposeDetailView,
    DockerComposeDownView,
    DockerComposeListCreateView,
    DockerComposeUpView,
    DockerDockerfileTemplateView,
    DockerImageListView,
    DockerImagePullView,
    DockerImageRemoveView,
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
    path("images/", DockerImageListView.as_view(), name="docker-image-list"),
    path("images/pull/", DockerImagePullView.as_view(), name="docker-image-pull"),
    path("images/remove/", DockerImageRemoveView.as_view(), name="docker-image-remove"),
    path("builds/", DockerBuildListCreateView.as_view(), name="docker-build-list"),
    path("builds/<int:pk>/", DockerBuildDetailView.as_view(), name="docker-build-detail"),
    path("compose/", DockerComposeListCreateView.as_view(), name="docker-compose-list"),
    path("compose/<int:pk>/", DockerComposeDetailView.as_view(), name="docker-compose-detail"),
    path("compose/<int:pk>/up/", DockerComposeUpView.as_view(), name="docker-compose-up"),
    path("compose/<int:pk>/down/", DockerComposeDownView.as_view(), name="docker-compose-down"),
    path("dockerfile-template/", DockerDockerfileTemplateView.as_view(), name="docker-dockerfile-template"),
]
