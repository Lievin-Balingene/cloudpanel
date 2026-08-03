from __future__ import annotations

from django.urls import path

from apps.databases.views import (
    DatabaseDetailView,
    DatabaseListCreateView,
    DatabaseOverviewView,
    DatabaseUserDetailView,
    DatabaseUserListCreateView,
    PrivilegeDeleteView,
    PrivilegeListCreateView,
)

urlpatterns = [
    path("overview/", DatabaseOverviewView.as_view(), name="databases-overview"),
    path("users/", DatabaseUserListCreateView.as_view(), name="databases-user-list"),
    path("users/<int:pk>/", DatabaseUserDetailView.as_view(), name="databases-user-detail"),
    path("privileges/", PrivilegeListCreateView.as_view(), name="databases-privilege-list"),
    path("privileges/<int:pk>/", PrivilegeDeleteView.as_view(), name="databases-privilege-delete"),
    path("", DatabaseListCreateView.as_view(), name="databases-list"),
    path("<int:pk>/", DatabaseDetailView.as_view(), name="databases-detail"),
]
