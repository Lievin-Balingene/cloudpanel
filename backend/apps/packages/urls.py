from __future__ import annotations

from django.urls import path

from apps.packages.views import (
    AssignPackageView,
    MyPackageView,
    PackageDetailView,
    PackageListCreateView,
    PulseAccountView,
    PulseMineView,
    PulseOverviewView,
    SeedPackagesView,
)

urlpatterns = [
    path("", PackageListCreateView.as_view(), name="package-list"),
    path("assign/", AssignPackageView.as_view(), name="package-assign"),
    path("seed/", SeedPackagesView.as_view(), name="package-seed"),
    path("mine/", MyPackageView.as_view(), name="package-mine"),
    path("pulse/", PulseOverviewView.as_view(), name="pulse-overview"),
    path("pulse/mine/", PulseMineView.as_view(), name="pulse-mine"),
    path("pulse/<int:user_id>/", PulseAccountView.as_view(), name="pulse-account"),
    path("<int:pk>/", PackageDetailView.as_view(), name="package-detail"),
]
