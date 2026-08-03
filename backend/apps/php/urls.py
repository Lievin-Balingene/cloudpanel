from __future__ import annotations

from django.urls import path

from apps.php.views import (
    PhpOverviewView,
    PhpSelectorDetailView,
    PhpSelectorListCreateView,
    PhpVersionDefaultView,
    PhpVersionDiscoverView,
    PhpVersionListView,
)

urlpatterns = [
    path("overview/", PhpOverviewView.as_view(), name="php-overview"),
    path("versions/", PhpVersionListView.as_view(), name="php-version-list"),
    path("versions/discover/", PhpVersionDiscoverView.as_view(), name="php-version-discover"),
    path("versions/<int:pk>/default/", PhpVersionDefaultView.as_view(), name="php-version-default"),
    path("selectors/", PhpSelectorListCreateView.as_view(), name="php-selector-list"),
    path("selectors/<int:pk>/", PhpSelectorDetailView.as_view(), name="php-selector-detail"),
]
