from __future__ import annotations

from django.urls import path

from apps.git_deploy.views import (
    GitCloneView,
    GitDeployView,
    GitKeygenView,
    GitLogListView,
    GitOverviewView,
    GitPullView,
    GitRepositoryDetailView,
    GitRepositoryListCreateView,
    GitRotateWebhookView,
    GitWebhookView,
)

urlpatterns = [
    path("overview/", GitOverviewView.as_view(), name="git-overview"),
    path("repos/", GitRepositoryListCreateView.as_view(), name="git-repo-list"),
    path("repos/<int:pk>/", GitRepositoryDetailView.as_view(), name="git-repo-detail"),
    path("repos/<int:pk>/clone/", GitCloneView.as_view(), name="git-repo-clone"),
    path("repos/<int:pk>/pull/", GitPullView.as_view(), name="git-repo-pull"),
    path("repos/<int:pk>/deploy/", GitDeployView.as_view(), name="git-repo-deploy"),
    path("repos/<int:pk>/keygen/", GitKeygenView.as_view(), name="git-repo-keygen"),
    path("repos/<int:pk>/rotate-webhook/", GitRotateWebhookView.as_view(), name="git-repo-rotate-webhook"),
    path("logs/", GitLogListView.as_view(), name="git-log-list"),
    path("webhook/<str:token>/", GitWebhookView.as_view(), name="git-webhook"),
]
