"""Management : republier toutes les zones DNS vers BIND."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.dns.authoritative import sync_all_zones_to_named


class Command(BaseCommand):
    help = "Exporte les zones DnsZone vers BIND (named) et demande un reload."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-glue",
            action="store_true",
            help="Ne pas créer/mettre à jour les A glue pour ns1/ns2",
        )

    def handle(self, *args, **options):
        count = sync_all_zones_to_named(ensure_glue=not options["no_glue"])
        self.stdout.write(self.style.SUCCESS(f"Zones DNS publiées: {count}"))
