"""Configuration Celery pour V-zone Panel."""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vzone.settings.development")

app = Celery("vzone")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:  # type: ignore[no-untyped-def]
    """Tâche de diagnostic Celery (utilisée par healthcheck)."""
    return f"Request: {self.request!r}"
