from __future__ import annotations

from django.urls import path

from apps.kubernetes.views import (
    KubernetesApplyView,
    KubernetesDeleteView,
    KubernetesOverviewView,
    KubernetesResourcesView,
)

urlpatterns = [
    path("overview/", KubernetesOverviewView.as_view(), name="kubernetes-overview"),
    path("resources/", KubernetesResourcesView.as_view(), name="kubernetes-resources"),
    path("apply/", KubernetesApplyView.as_view(), name="kubernetes-apply"),
    path("delete/", KubernetesDeleteView.as_view(), name="kubernetes-delete"),
]
