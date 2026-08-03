from __future__ import annotations

from django.urls import path

from apps.dns.views import (
    DnsRecordDetailView,
    DnsRecordListCreateView,
    DnsZoneDetailView,
    DnsZoneListCreateView,
    DnssecToggleView,
)

urlpatterns = [
    path("zones/", DnsZoneListCreateView.as_view(), name="dns-zone-list"),
    path("zones/<int:pk>/", DnsZoneDetailView.as_view(), name="dns-zone-detail"),
    path("zones/<int:pk>/dnssec/", DnssecToggleView.as_view(), name="dns-zone-dnssec"),
    path(
        "zones/<int:zone_id>/records/",
        DnsRecordListCreateView.as_view(),
        name="dns-record-list",
    ),
    path(
        "zones/<int:zone_id>/records/<int:pk>/",
        DnsRecordDetailView.as_view(),
        name="dns-record-detail",
    ),
]
