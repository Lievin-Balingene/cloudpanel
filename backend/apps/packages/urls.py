from __future__ import annotations

from django.urls import path

from apps.packages.views import (
    AssignPackageView,
    MyPackageView,
    PackageDetailView,
    PackageListCreateView,
    SeedPackagesView,
)

urlpatterns = [
    path("", PackageListCreateView.as_view(), name="package-list"),
    path("assign/", AssignPackageView.as_view(), name="package-assign"),
    path("seed/", SeedPackagesView.as_view(), name="package-seed"),
    path("mine/", MyPackageView.as_view(), name="package-mine"),
    path("<int:pk>/", PackageDetailView.as_view(), name="package-detail"),
]
