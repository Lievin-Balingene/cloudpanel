"""Relance les apps Python RUNNING dont le process est mort (évite 502 nginx)."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.python_apps.services import reconcile_python_apps


class Command(BaseCommand):
    help = "Reconcile Python apps: restart RUNNING apps with dead process/port"

    def handle(self, *args, **options):
        result = reconcile_python_apps()
        self.stdout.write(self.style.SUCCESS(str(result)))
