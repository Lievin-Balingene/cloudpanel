"""Management : audite / valide toutes les zones DNS (anti-SERVFAIL)."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.dns.authoritative import (
    TXT_MAX_OCTETS,
    audit_zone_records,
    dns_zones_dir,
    render_zone_file,
    validate_zone_export,
)
from apps.dns.models import DnsZone


class Command(BaseCommand):
    help = (
        "Valide chaque zone active (TXT ≤ 255 octets, SOA, etc.). "
        "Exit 1 si une zone provoquerait un SERVFAIL BIND."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix-files",
            action="store_true",
            help="Valider aussi les fichiers .zone déjà sur disque",
        )

    def handle(self, *args, **options):
        issues = audit_zone_records()
        if options["disk_files"]:
            zdir = dns_zones_dir()
            if zdir.is_dir():
                for path in sorted(zdir.glob("*.zone")):
                    try:
                        content = path.read_text(encoding="utf-8")
                    except OSError as exc:
                        issues.append(f"{path.name}: lecture impossible ({exc})")
                        continue
                    issues.extend(
                        validate_zone_export(content, zone_name=path.stem)
                    )

        # Résumé TXT longs côté DB (avant chunking — info)
        long_txt = 0
        for zone in DnsZone.objects.filter(is_active=True).prefetch_related("records"):
            for rec in zone.records.all():
                if rec.record_type.upper() != "TXT" or not rec.is_active:
                    continue
                if len((rec.content or "").encode("utf-8")) > TXT_MAX_OCTETS:
                    long_txt += 1
                    # Doit passer après render (chunking)
                    rendered = render_zone_file(zone)
                    still_bad = validate_zone_export(rendered, zone_name=zone.name)
                    if still_bad:
                        issues.extend(still_bad)

        self.stdout.write(
            f"Zones actives: {DnsZone.objects.filter(is_active=True).count()}; "
            f"TXT >{TXT_MAX_OCTETS} octets en DB (OK si chunkés): {long_txt}"
        )

        if issues:
            for msg in issues:
                self.stderr.write(self.style.ERROR(msg))
            raise CommandError(f"{len(issues)} problème(s) DNS détecté(s)")

        self.stdout.write(self.style.SUCCESS("Toutes les zones sont valides (anti-SERVFAIL OK)."))
