"""Tests export zone BIND."""
from __future__ import annotations

import pytest

from apps.accounts.factories import UserFactory
from apps.dns.authoritative import render_zone_file, write_zone_file, write_zones_conf
from apps.dns.models import DnsRecord
from apps.dns.services import create_zone_with_defaults


@pytest.mark.unit
@pytest.mark.django_db
def test_render_zone_includes_soa_ns_and_a(tmp_path, settings):
    settings.VZONE_DNS_ZONES_DIR = str(tmp_path / "zones")
    settings.VZONE_DNS_ZONES_CONF = str(tmp_path / "zones.conf")
    settings.VZONE_DNS_RELOAD_FLAG = str(tmp_path / "reload.requested")
    settings.VZONE_PUBLIC_IP = "203.0.113.50"

    user = UserFactory()
    zone = create_zone_with_defaults(name="client.example.com", owner=user)
    DnsRecord.objects.create(
        zone=zone,
        record_type="A",
        name="@",
        content="203.0.113.50",
        ttl=14400,
    )
    DnsRecord.objects.create(
        zone=zone,
        record_type="A",
        name="www",
        content="203.0.113.50",
        ttl=14400,
    )
    zone.bump_serial()

    text = render_zone_file(zone)
    assert "IN SOA" in text
    assert "IN\tNS\t" in text or "IN NS" in text.replace("\t", " ")
    assert "203.0.113.50" in text
    assert "www" in text

    path = write_zone_file(zone)
    assert path is not None and path.exists()
    conf = write_zones_conf([zone])
    assert conf.exists()
    assert 'zone "client.example.com"' in conf.read_text(encoding="utf-8")
