"""API V-zone AI Deployment Assistant."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_assistant.models import Conversation
from apps.ai_assistant.providers import get_provider
from apps.ai_assistant.serializers import (
    ConfirmActionSerializer,
    ConversationDetailSerializer,
    ConversationSerializer,
    SendMessageSerializer,
)
from apps.ai_assistant.services import (
    confirm_pending_action,
    conversations_qs,
    create_conversation,
    refresh_context,
    send_message,
)
from apps.ai_assistant.tools import ensure_tools_loaded, list_tool_specs
from apps.ai_assistant.services.playbooks import list_playbooks
from apps.ai_assistant.services.jail_commands import list_jail_catalog
from apps.core.exceptions import VZoneAPIException


def _client_ip(request: Request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AiStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        ensure_tools_loaded()
        provider = get_provider()
        from apps.ai_assistant.providers.ollama import circuit_status

        return Response(
            {
                "success": True,
                "data": {
                    "provider": getattr(provider, "name", "unknown"),
                    "available": bool(provider.is_available()),
                    "ollama_circuit": circuit_status(),
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "dangerous": t.dangerous,
                        }
                        for t in list_tool_specs()
                    ],
                    "playbooks": list_playbooks(),
                    "jail_commands": list_jail_catalog(),
                },
            }
        )


class AiPlaybooksView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": list_playbooks()})


class ConversationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = conversations_qs(request.user)[:50]
        return Response(
            {
                "success": True,
                "data": ConversationSerializer(qs, many=True).data,
            }
        )

    def post(self, request: Request) -> Response:
        title = str(request.data.get("title") or "").strip()
        conv = create_conversation(request.user, title=title)
        return Response(
            {"success": True, "data": ConversationDetailSerializer(conv).data},
            status=status.HTTP_201_CREATED,
        )


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        conv = get_object_or_404(conversations_qs(request.user), pk=pk)
        refresh_context(conv)
        return Response(
            {"success": True, "data": ConversationDetailSerializer(conv).data}
        )

    def delete(self, request: Request, pk: int) -> Response:
        conv = get_object_or_404(conversations_qs(request.user), pk=pk)
        conv.status = Conversation.Status.ARCHIVED
        conv.save(update_fields=["status", "updated_at"])
        return Response({"success": True, "data": {"archived": True}})


class ConversationMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        ser = SendMessageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        conv = get_object_or_404(
            conversations_qs(request.user).exclude(status=Conversation.Status.ARCHIVED),
            pk=pk,
        )
        try:
            result = send_message(
                request.user,
                conv,
                ser.validated_data["message"],
                ip_address=_client_ip(request),
                ui_context=ser.validated_data.get("ui_context") or {},
            )
        except VZoneAPIException as exc:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": getattr(exc, "default_code", None) or "error",
                        "message": str(exc.detail),
                    },
                },
                status=int(getattr(exc, "status_code", 400) or 400),
            )
        return Response({"success": True, "data": result})


class ConfirmActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        ser = ConfirmActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = confirm_pending_action(
            user=request.user,
            token=ser.validated_data["token"],
            confirm=bool(ser.validated_data["confirm"]),
            ip_address=_client_ip(request),
        )
        ok = bool(result.get("ok") or result.get("cancelled"))
        return Response(
            {"success": ok, "data": result},
            status=status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST,
        )
