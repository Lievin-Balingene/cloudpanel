"""Routes WebSocket globales — chaque module enregistre ses consumers."""
from __future__ import annotations

from django.urls import path

from apps.core.consumers import SystemMetricsConsumer

websocket_urlpatterns = [
    path("ws/metrics/", SystemMetricsConsumer.as_asgi()),
]
