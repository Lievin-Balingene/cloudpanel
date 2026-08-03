"""Tâches Celery SSL."""
from __future__ import annotations

from celery import shared_task

from apps.domains.ssl_services import renew_due_certificates


@shared_task(name="domains.renew_ssl_certificates")
def renew_ssl_certificates() -> dict:
    return renew_due_certificates()
