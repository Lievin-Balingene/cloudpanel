from __future__ import annotations

from django.urls import path

from apps.monitoring.views import (
    AlertEventAcknowledgeView,
    AlertEventListView,
    AlertEventResolveView,
    AlertRuleDetailView,
    AlertRuleListCreateView,
    MonitoringEvaluateView,
    MonitoringOverviewView,
)

urlpatterns = [
    path("overview/", MonitoringOverviewView.as_view(), name="monitoring-overview"),
    path("rules/", AlertRuleListCreateView.as_view(), name="monitoring-rule-list"),
    path("rules/<int:pk>/", AlertRuleDetailView.as_view(), name="monitoring-rule-detail"),
    path("events/", AlertEventListView.as_view(), name="monitoring-event-list"),
    path(
        "events/<int:pk>/acknowledge/",
        AlertEventAcknowledgeView.as_view(),
        name="monitoring-event-ack",
    ),
    path(
        "events/<int:pk>/resolve/",
        AlertEventResolveView.as_view(),
        name="monitoring-event-resolve",
    ),
    path("evaluate/", MonitoringEvaluateView.as_view(), name="monitoring-evaluate"),
]
