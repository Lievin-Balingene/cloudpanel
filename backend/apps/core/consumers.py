"""Consumer WebSocket pour les métriques temps réel."""
from __future__ import annotations

import asyncio
import json
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.core.services import collect_system_metrics

logger = logging.getLogger(__name__)


class SystemMetricsConsumer(AsyncJsonWebsocketConsumer):
    """Diffuse les métriques système toutes les 2 secondes aux admins connectés."""

    INTERVAL_SECONDS = 2.0

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or user.is_anonymous or getattr(user, "role", None) != "administrator":
            await self.close(code=4403)
            return
        await self.accept()
        self._running = True
        self._task = asyncio.create_task(self._stream_metrics())

    async def disconnect(self, code: int) -> None:
        self._running = False
        task = getattr(self, "_task", None)
        if task:
            task.cancel()

    async def _stream_metrics(self) -> None:
        while getattr(self, "_running", False):
            try:
                metrics = await asyncio.to_thread(collect_system_metrics)
                await self.send_json({"type": "metrics", "data": metrics})
            except Exception:  # noqa: BLE001
                logger.exception("Échec diffusion métriques WebSocket")
                await self.send(
                    text_data=json.dumps(
                        {"type": "error", "message": "Impossible de collecter les métriques."}
                    )
                )
            await asyncio.sleep(self.INTERVAL_SECONDS)
