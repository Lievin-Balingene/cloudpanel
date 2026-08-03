"""Tâches Celery dashboard."""
from __future__ import annotations

from celery import shared_task

from apps.dashboard.services import capture_snapshot, prune_snapshots


@shared_task(name="dashboard.capture_resource_snapshot")
def capture_resource_snapshot() -> str:
    snap = capture_snapshot()
    prune_snapshots(retain_hours=72)
    try:
        from apps.monitoring.services import evaluate_rules

        evaluate_rules()
    except Exception:
        # Le monitoring ne doit pas faire échouer la capture
        pass
    return snap.collected_at.isoformat()
