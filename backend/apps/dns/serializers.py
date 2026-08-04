from __future__ import annotations

from rest_framework import serializers

from apps.dns.models import RECORD_TYPES, DnsRecord, DnsZone, normalize_zone_name


class DnsRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = DnsRecord
        fields = (
            "id",
            "zone",
            "record_type",
            "name",
            "content",
            "ttl",
            "priority",
            "weight",
            "port",
            "flags",
            "tag",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "zone", "created_at", "updated_at")

    def validate_record_type(self, value: str) -> str:
        allowed = {t[0] for t in RECORD_TYPES}
        if value not in allowed:
            raise serializers.ValidationError(f"Type non supporté: {value}")
        return value

    def validate(self, attrs: dict) -> dict:
        instance = getattr(self, "instance", None)
        rtype = attrs.get("record_type") or (instance.record_type if instance else None)
        name = attrs.get("name") if "name" in attrs else (instance.name if instance else "@")
        priority = attrs.get("priority") if "priority" in attrs else (instance.priority if instance else None)
        weight = attrs.get("weight") if "weight" in attrs else (instance.weight if instance else None)
        port = attrs.get("port") if "port" in attrs else (instance.port if instance else None)
        tag = attrs.get("tag") if "tag" in attrs else (instance.tag if instance else "")

        if rtype in {"MX", "SRV"} and priority is None:
            raise serializers.ValidationError({"priority": "Priorité requise."})
        if rtype == "SRV" and (weight is None or port is None):
            raise serializers.ValidationError("Weight et port requis pour SRV.")
        if rtype == "CAA" and not tag:
            raise serializers.ValidationError({"tag": "Tag CAA requis."})
        if rtype == "CNAME" and name in {"@", ""}:
            raise serializers.ValidationError({"name": "CNAME apex interdit."})
        return attrs


class DnsZoneSerializer(serializers.ModelSerializer):
    records = DnsRecordSerializer(many=True, read_only=True)
    record_count = serializers.SerializerMethodField()
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = DnsZone
        fields = (
            "id",
            "name",
            "owner",
            "owner_username",
            "ttl_default",
            "soa_primary_ns",
            "soa_admin_email",
            "soa_serial",
            "soa_refresh",
            "soa_retry",
            "soa_expire",
            "soa_minimum",
            "dnssec_enabled",
            "dnssec_algorithm",
            "is_active",
            "notes",
            "records",
            "record_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "soa_serial",
            "records",
            "record_count",
            "created_at",
            "updated_at",
        )

    def get_record_count(self, obj: DnsZone) -> int:
        return obj.records.count()

    def validate_name(self, value: str) -> str:
        try:
            return normalize_zone_name(value)
        except Exception as exc:  # noqa: BLE001
            raise serializers.ValidationError(str(exc)) from exc


class DnsZoneCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    owner_id = serializers.IntegerField(required=False)
    primary_ns = serializers.CharField(required=False, allow_blank=True)
    secondary_ns = serializers.CharField(required=False, allow_blank=True)
    admin_email = serializers.CharField(required=False, allow_blank=True)
