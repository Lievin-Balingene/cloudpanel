"""Tâches Celery monitoring."""
from __future__ import annotations

from celery import shared_task

from apps.monitoring.services import evaluate_rules


@shared_task(name="monitoring.evaluate_alert_rules")
def evaluate_alert_rules() -> dict:
    return evaluate_rules()
