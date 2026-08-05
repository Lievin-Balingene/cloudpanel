"""Tests export zone BIND + garde-fous anti-SERVFAIL."""
from __future__ import annotations

import re

import pytest

from apps.accounts.factories import UserFactory
from apps.dns.authoritative import (
    TXT_MAX_OCTETS,
    _txt_rdata,
    assert_zone_export_safe,
    render_zone_file,
    sync_all_zones_to_named,
    validate_zone_export,
    write_zone_file,
    write_zones_conf,
)
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
    assert_zone_export_safe(text, zone_name=zone.name)

    path = write_zone_file(zone)
    assert path is not None and path.exists()
    conf = write_zones_conf([zone])
    assert conf.exists()
    assert 'zone "client.example.com"' in conf.read_text(encoding="utf-8")


@pytest.mark.unit
@pytest.mark.django_db
def test_long_txt_is_chunked_for_bind(tmp_path, settings):
    """DKIM RSA-2048 > 255 octets : BIND exige plusieurs chaînes TXT."""
    settings.VZONE_DNS_ZONES_DIR = str(tmp_path / "zones")
    settings.VZONE_DNS_ZONES_CONF = str(tmp_path / "zones.conf")
    settings.VZONE_DNS_RELOAD_FLAG = str(tmp_path / "reload.requested")

    long_key = "A" * 400
    dkim = f"v=DKIM1; k=rsa; p={long_key}"
    rdata = _txt_rdata(dkim)
    parts = re.findall(r'"((?:\\.|[^"\\])*)"', rdata)
    assert len(parts) >= 2
    assert all(len(p.encode("utf-8")) <= TXT_MAX_OCTETS for p in parts)
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
    assert "default._domainkey" in text
    assert validate_zone_export(text, zone_name=zone.name) == []
    path = write_zone_file(zone)
    assert path is not None


@pytest.mark.unit
@pytest.mark.django_db
def test_real_dkim_key_never_breaks_zone_export(tmp_path, settings):
    """Régression : clé RSA-2048 réelle (comme enable_dkim) doit toujours exporter."""
    from apps.email.services import generate_dkim_keys

    settings.VZONE_DNS_ZONES_DIR = str(tmp_path / "zones")
    settings.VZONE_DNS_ZONES_CONF = str(tmp_path / "zones.conf")
    settings.VZONE_DNS_RELOAD_FLAG = str(tmp_path / "reload.requested")

    _priv, public_b64 = generate_dkim_keys()
    dkim = f"v=DKIM1; k=rsa; p={public_b64}"
    assert len(dkim.encode("utf-8")) > TXT_MAX_OCTETS

    user = UserFactory()
    zone = create_zone_with_defaults(name="mailsafe.example.com", owner=user)
    DnsRecord.objects.create(
        zone=zone,
        record_type="TXT",
        name="default._domainkey",
        content=dkim,
        ttl=3600,
    )
    text = render_zone_file(zone)
    assert_zone_export_safe(text, zone_name=zone.name)
    assert write_zone_file(zone) is not None

    result = sync_all_zones_to_named(ensure_glue=False)
    assert result.ok
    assert result.published >= 1
    assert (tmp_path / "zones" / "mailsafe.example.com.zone").exists()


@pytest.mark.unit
def test_validate_rejects_unchunked_long_txt():
    bad = (
        '$TTL 14400\n$ORIGIN bad.example.\n'
        '@ IN SOA ns1.example. hostmaster.example. ( 1 3600 1800 1209600 86400 )\n'
        f'@\t3600\tIN\tTXT\t"{"X" * 300}"\n'
    )
    errors = validate_zone_export(bad, zone_name="bad.example")
    assert errors
    assert any("255" in e for e in errors)
