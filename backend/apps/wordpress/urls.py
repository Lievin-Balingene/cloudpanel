from __future__ import annotations

from django.urls import path

from apps.wordpress.views import (
    WordPressOverviewView,
    WordPressSiteDetailView,
    WordPressSiteListCreateView,
)

urlpatterns = [
    path("overview/", WordPressOverviewView.as_view(), name="wordpress-overview"),
    path("sites/", WordPressSiteListCreateView.as_view(), name="wordpress-site-list"),
    path("sites/<int:pk>/", WordPressSiteDetailView.as_view(), name="wordpress-site-detail"),
]
