"""Routes WebSocket globales — chaque module enregistre ses consumers."""
from __future__ import annotations

from django.urls import path

from apps.core.consumers import SystemMetricsConsumer
from apps.core.terminal_consumer import WebTerminalConsumer

websocket_urlpatterns = [
    path("ws/metrics/", SystemMetricsConsumer.as_asgi()),
    path("ws/terminal/", WebTerminalConsumer.as_asgi()),
]
