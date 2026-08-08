"""Tools DNS (zones + enregistrements + DNSSEC)."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


def _record_summary(rec) -> dict[str, Any]:
    return {
        "id": rec.pk,
        "zone_id": rec.zone_id,
        "record_type": rec.record_type,
        "name": rec.name,
        "content": (rec.content or "")[:500],
        "ttl": rec.ttl,
        "priority": rec.priority,
        "weight": rec.weight,
        "port": rec.port,
        "flags": rec.flags,
        "tag": rec.tag or "",
        "is_active": rec.is_active,
    }


@register_tool(
    name="list_dns_zones",
    description="Liste les zones DNS du compte avec le nombre d'enregistrements.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_dns_zones(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.dns.services import zones_queryset_for

    zones = []
    for z in zones_queryset_for(user)[:80]:
        zones.append(
            {
                "id": z.pk,
                "name": z.name,
                "soa_serial": z.soa_serial,
                "dnssec_enabled": bool(getattr(z, "dnssec_enabled", False)),
                "is_active": getattr(z, "is_active", True),
                "record_count": z.records.count() if hasattr(z, "records") else 0,
            }
        )
    return ok(zones=zones, count=len(zones))


@register_tool(
    name="create_dns_zone",
    description="Crée une zone DNS avec enregistrements NS par défaut (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "primary_ns": {"type": "string"},
            "secondary_ns": {"type": "string"},
            "admin_email": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_dns_zone(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.dns.services import create_zone_with_defaults

    name = require_str(params, "name", max_len=253)
    if not name:
        return err("name requis")

    def _run():
        zone = create_zone_with_defaults(
            name=name,
            owner=user,
            primary_ns=require_str(params, "primary_ns", max_len=253) or None,
            secondary_ns=require_str(params, "secondary_ns", max_len=253) or None,
            admin_email=require_str(params, "admin_email", max_len=253) or None,
        )
        return {"id": zone.pk, "name": zone.name, "soa_serial": zone.soa_serial}

    return run_service(_run)


@register_tool(
    name="list_dns_records",
    description="Liste les enregistrements DNS d'une zone appartenant au compte.",
    parameters={
        "type": "object",
        "properties": {"zone_id": {"type": "integer"}},
        "required": ["zone_id"],
        "additionalProperties": False,
    },
)
def list_dns_records(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.dns.models import DnsRecord
    from apps.dns.services import zones_queryset_for

    zone = zones_queryset_for(user).filter(pk=require_int(params, "zone_id")).first()
    if not zone:
        return err("Zone DNS introuvable", "not_found")
    records = [_record_summary(r) for r in DnsRecord.objects.filter(zone=zone)[:200]]
    return ok(zone_id=zone.pk, zone_name=zone.name, records=records, count=len(records))


@register_tool(
    name="upsert_dns_record",
    description="Crée ou met à jour un enregistrement DNS sur une zone du compte (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "zone_id": {"type": "integer"},
            "record_id": {"type": "integer"},
            "record_type": {"type": "string"},
            "name": {"type": "string"},
            "content": {"type": "string"},
            "ttl": {"type": "integer"},
            "priority": {"type": "integer"},
            "weight": {"type": "integer"},
            "port": {"type": "integer"},
            "flags": {"type": "integer"},
            "tag": {"type": "string"},
            "is_active": {"type": "boolean"},
        },
        "required": ["zone_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def upsert_dns_record(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.core.exceptions import VZoneAPIException
    from apps.dns.models import DnsRecord
    from apps.dns.services import zones_queryset_for

    zone = zones_queryset_for(user).filter(pk=require_int(params, "zone_id")).first()
    if not zone:
        return err("Zone DNS introuvable", "not_found")

    record_id = require_int(params, "record_id")
    if record_id:
        existing = DnsRecord.objects.filter(pk=record_id, zone=zone).first()
        if not existing:
            return err("Enregistrement introuvable", "not_found")

    def _run():
        if record_id:
            record = DnsRecord.objects.filter(pk=record_id, zone=zone).first()
            if not record:
                raise VZoneAPIException(detail="Enregistrement introuvable", code="not_found", status_code=404)
            for key in ("record_type", "name", "content", "tag"):
                if key in params and params[key] is not None:
                    setattr(record, key, params[key] if key != "name" else (str(params[key]).strip() or "@"))
            for key in ("ttl", "priority", "weight", "port", "flags"):
                if key in params:
                    setattr(record, key, require_int(params, key))
            if "is_active" in params:
                record.is_active = bool(params["is_active"])
            record.save()
        else:
            rtype = require_str(params, "record_type", max_len=8)
            content = str(params.get("content") or "").strip()
            if not rtype or not content:
                raise VZoneAPIException(
                    detail="record_type et content requis pour créer",
                    code="invalid_params",
                    status_code=400,
                )
            record = DnsRecord.objects.create(
                zone=zone,
                record_type=rtype.upper(),
                name=require_str(params, "name", default="@", max_len=255) or "@",
                content=content,
                ttl=require_int(params, "ttl"),
                priority=require_int(params, "priority"),
                weight=require_int(params, "weight"),
                port=require_int(params, "port"),
                flags=require_int(params, "flags"),
                tag=require_str(params, "tag", max_len=32),
                is_active=bool(params["is_active"]) if "is_active" in params else True,
            )
        if hasattr(zone, "bump_serial"):
            zone.bump_serial()
        try:
            from apps.dns.authoritative import schedule_zone_sync

            schedule_zone_sync(zone)
        except Exception:  # noqa: BLE001
            pass
        return _record_summary(record)

    return run_service(_run)


@register_tool(
    name="delete_dns_record",
    description="Supprime un enregistrement DNS (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "zone_id": {"type": "integer"},
            "record_id": {"type": "integer"},
        },
        "required": ["zone_id", "record_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_dns_record(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.dns.models import DnsRecord
    from apps.dns.services import zones_queryset_for

    zone = zones_queryset_for(user).filter(pk=require_int(params, "zone_id")).first()
    if not zone:
        return err("Zone DNS introuvable", "not_found")
    record = DnsRecord.objects.filter(pk=require_int(params, "record_id"), zone=zone).first()
    if not record:
        return err("Enregistrement introuvable", "not_found")
    rid = record.pk

    def _run():
        record.delete()
        if hasattr(zone, "bump_serial"):
            zone.bump_serial()
        try:
            from apps.dns.authoritative import schedule_zone_sync

            schedule_zone_sync(zone)
        except Exception:  # noqa: BLE001
            pass
        return {"deleted": rid}

    return run_service(_run)


@register_tool(
    name="toggle_dnssec",
    description="Active ou désactive DNSSEC sur une zone (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "zone_id": {"type": "integer"},
            "enabled": {"type": "boolean"},
        },
        "required": ["zone_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def toggle_dnssec(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.dns.services import zones_queryset_for

    zone = zones_queryset_for(user).filter(pk=require_int(params, "zone_id")).first()
    if not zone:
        return err("Zone DNS introuvable", "not_found")
    if not hasattr(zone, "dnssec_enabled"):
        return err("DNSSEC non supporté sur ce modèle", "unsupported")

    def _run():
        enable = bool(params["enabled"]) if "enabled" in params else (not zone.dnssec_enabled)
        zone.dnssec_enabled = enable
        if hasattr(zone, "dnssec_algorithm"):
            zone.dnssec_algorithm = "RSASHA256" if enable else ""
            zone.save(update_fields=["dnssec_enabled", "dnssec_algorithm", "updated_at"])
        else:
            zone.save(update_fields=["dnssec_enabled", "updated_at"])
        if hasattr(zone, "bump_serial"):
            zone.bump_serial()
        try:
            from apps.dns.authoritative import schedule_zone_sync

            schedule_zone_sync(zone)
        except Exception:  # noqa: BLE001
            pass
        return {
            "id": zone.pk,
            "name": zone.name,
            "dnssec_enabled": zone.dnssec_enabled,
            "dnssec_algorithm": getattr(zone, "dnssec_algorithm", ""),
        }

    return run_service(_run)
