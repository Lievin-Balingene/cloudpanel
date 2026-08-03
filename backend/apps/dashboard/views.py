from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdministrator
from apps.dashboard.services import capture_snapshot, history, overview_for


class DashboardOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class DashboardHistoryView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        hours = int(request.query_params.get("hours", 24))
        hours = max(1, min(hours, 168))
        return Response({"success": True, "data": history(hours=hours)})


class DashboardCaptureView(APIView):
    """Capture manuelle (WHM) — utile sans Celery en dev."""

    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        snap = capture_snapshot()
        return Response(
            {
                "success": True,
                "data": {
                    "collected_at": snap.collected_at.isoformat(),
                    "cpu_percent": snap.cpu_percent,
                    "ram_percent": snap.ram_percent,
                    "disk_percent": snap.disk_percent,
                },
            }
        )
