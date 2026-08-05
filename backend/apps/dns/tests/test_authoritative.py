"""Tests export zone BIND."""
from __future__ import annotations

import re

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


@pytest.mark.unit
@pytest.mark.django_db
def test_long_txt_is_chunked_for_bind(tmp_path, settings):
    """DKIM RSA-2048 > 255 octets : BIND exige plusieurs chaînes TXT."""
    from apps.dns.authoritative import _txt_rdata

    settings.VZONE_DNS_ZONES_DIR = str(tmp_path / "zones")
    settings.VZONE_DNS_ZONES_CONF = str(tmp_path / "zones.conf")
    settings.VZONE_DNS_RELOAD_FLAG = str(tmp_path / "reload.requested")

    long_key = "A" * 400
    dkim = f"v=DKIM1; k=rsa; p={long_key}"
    rdata = _txt_rdata(dkim)
    parts = re.findall(r'"([^"]*)"', rdata)
    assert len(parts) >= 2
    assert all(len(p) <= 255 for p in parts)
    assert "".join(parts) == dkim

    user = UserFactory()
    zone = create_zone_with_defaults(name="dkim.example.com", owner=user)
    DnsRecord.objects.create(
        zone=zone,
        record_type="TXT",
        name="default._domainkey",
        content=dkim,
        ttl=3600,
    )
    text = render_zone_file(zone)
    assert 'default._domainkey' in text
    assert text.count('"') >= 4  # au moins 2 chaînes
    # Aucune chaîne entre guillemets > 255
    for m in re.finditer(r'"([^"]*)"', text):
        assert len(m.group(1)) <= 255
