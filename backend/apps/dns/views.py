"""API DNS zones & records."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.dns.models import DnsRecord, DnsZone
from apps.dns.serializers import (
    DnsRecordSerializer,
    DnsZoneCreateSerializer,
    DnsZoneSerializer,
)
from apps.dns.services import create_zone_with_defaults, zones_queryset_for


class DnsZoneListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = zones_queryset_for(request.user)
        data = DnsZoneSerializer(qs, many=True).data
        return Response({"success": True, "data": data})

    def post(self, request: Request) -> Response:
        serializer = DnsZoneCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner = request.user
        owner_id = serializer.validated_data.get("owner_id")
        if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
            owner = get_object_or_404(User, pk=owner_id)
            if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
                return Response(status=status.HTTP_403_FORBIDDEN)
        if DnsZone.objects.filter(name=serializer.validated_data["name"].lower().rstrip(".")).exists():
            return Response(
                {
                    "success": False,
                    "error": {"code": "exists", "message": "Cette zone existe déjà."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        zone = create_zone_with_defaults(
            name=serializer.validated_data["name"],
            owner=owner,
            primary_ns=serializer.validated_data.get("primary_ns") or None,
            secondary_ns=serializer.validated_data.get("secondary_ns") or None,
            admin_email=serializer.validated_data.get("admin_email") or None,
        )
        from apps.dns.authoritative import schedule_zone_sync

        schedule_zone_sync(zone)
        return Response(
            {"success": True, "data": DnsZoneSerializer(zone).data},
            status=status.HTTP_201_CREATED,
        )


class DnsZoneDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request: Request, pk: int) -> DnsZone:
        return get_object_or_404(zones_queryset_for(request.user), pk=pk)

    def get(self, request: Request, pk: int) -> Response:
        zone = self._get(request, pk)
        return Response({"success": True, "data": DnsZoneSerializer(zone).data})

    def patch(self, request: Request, pk: int) -> Response:
        zone = self._get(request, pk)
        serializer = DnsZoneSerializer(zone, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        from apps.dns.authoritative import schedule_zone_sync

        schedule_zone_sync(zone)
        return Response({"success": True, "data": serializer.data})

    def delete(self, request: Request, pk: int) -> Response:
        zone = self._get(request, pk)
        zone_name = zone.name
        zone.delete()
        from apps.dns.authoritative import schedule_zone_sync

        schedule_zone_sync(zone_name=zone_name)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DnsRecordListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, zone_id: int) -> Response:
        zone = get_object_or_404(zones_queryset_for(request.user), pk=zone_id)
        records = zone.records.all()
        return Response({"success": True, "data": DnsRecordSerializer(records, many=True).data})

    def post(self, request: Request, zone_id: int) -> Response:
        zone = get_object_or_404(zones_queryset_for(request.user), pk=zone_id)
        serializer = DnsRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = serializer.save(zone=zone)
        zone.bump_serial()
        from apps.dns.authoritative import schedule_zone_sync

        schedule_zone_sync(zone)
        return Response(
            {"success": True, "data": DnsRecordSerializer(record).data},
            status=status.HTTP_201_CREATED,
        )


class DnsRecordDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_record(self, request: Request, zone_id: int, pk: int) -> DnsRecord:
        zone = get_object_or_404(zones_queryset_for(request.user), pk=zone_id)
        return get_object_or_404(DnsRecord, pk=pk, zone=zone)

    def patch(self, request: Request, zone_id: int, pk: int) -> Response:
        record = self._get_record(request, zone_id, pk)
        serializer = DnsRecordSerializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record.zone.bump_serial()
        from apps.dns.authoritative import schedule_zone_sync

        schedule_zone_sync(record.zone)
        return Response({"success": True, "data": serializer.data})

    def delete(self, request: Request, zone_id: int, pk: int) -> Response:
        record = self._get_record(request, zone_id, pk)
        zone = record.zone
        record.delete()
        zone.bump_serial()
        from apps.dns.authoritative import schedule_zone_sync

        schedule_zone_sync(zone)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DnssecToggleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        zone = get_object_or_404(zones_queryset_for(request.user), pk=pk)
        enable = bool(request.data.get("enabled", not zone.dnssec_enabled))
        zone.dnssec_enabled = enable
        zone.dnssec_algorithm = "RSASHA256" if enable else ""
        zone.save(update_fields=["dnssec_enabled", "dnssec_algorithm", "updated_at"])
        zone.bump_serial()
        from apps.dns.authoritative import schedule_zone_sync

        schedule_zone_sync(zone)
        return Response({"success": True, "data": DnsZoneSerializer(zone).data})
