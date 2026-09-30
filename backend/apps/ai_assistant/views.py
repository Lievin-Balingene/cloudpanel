"""API V-zone AI Deployment Assistant."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_assistant.models import Conversation
from apps.ai_assistant.serializers import (
    AiProviderSettingsSerializer,
    AiProviderTestSerializer,
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
from apps.ai_assistant.services.provider_resolve import (
    byok_feature_enabled,
    get_or_create_settings,
    get_provider_for_user,
    provider_source_for_user,
    reset_user_provider_settings,
    settings_public_dict,
    test_user_provider,
    update_user_provider_settings,
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
        provider = get_provider_for_user(request.user)
        from apps.ai_assistant.providers.ollama import circuit_status

        byok_settings = None
        if byok_feature_enabled():
            byok_settings = settings_public_dict(get_or_create_settings(request.user))

        return Response(
            {
                "success": True,
                "data": {
                    "provider": getattr(provider, "name", "unknown"),
                    "model": getattr(provider, "model", "") or "",
                    "available": bool(provider.is_available())
                    or getattr(provider, "name", "") == "mock",
                    "provider_source": provider_source_for_user(request.user),
                    "byok_enabled": byok_feature_enabled(),
                    "byok": byok_settings,
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


class AiProviderSettingsView(APIView):
    """GET/PUT/DELETE — config BYOK du client authentifié."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        data = {
            "byok_enabled": byok_feature_enabled(),
            "settings": settings_public_dict(
                get_or_create_settings(request.user) if byok_feature_enabled() else None
            ),
            "provider_source": provider_source_for_user(request.user),
            "active_provider": getattr(get_provider_for_user(request.user), "name", "unknown"),
            "active_model": getattr(get_provider_for_user(request.user), "model", "") or "",
        }
        return Response({"success": True, "data": data})

    def put(self, request: Request) -> Response:
        ser = AiProviderSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        try:
            obj = update_user_provider_settings(
                request.user,
                mode=vd["mode"],
                base_url=vd.get("base_url") or "",
                model_name=vd.get("model_name") or "",
                api_key=vd.get("api_key") if vd.get("api_key") else None,
                clear_api_key=bool(vd.get("clear_api_key")),
                enabled=bool(vd.get("enabled", True)),
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
        provider = get_provider_for_user(request.user)
        return Response(
            {
                "success": True,
                "data": {
                    "settings": settings_public_dict(obj),
                    "provider_source": provider_source_for_user(request.user),
                    "active_provider": getattr(provider, "name", "unknown"),
                    "active_model": getattr(provider, "model", "") or "",
                },
            }
        )

    def delete(self, request: Request) -> Response:
        obj = reset_user_provider_settings(request.user)
        return Response(
            {
                "success": True,
                "data": {
                    "settings": settings_public_dict(obj),
                    "provider_source": "server",
                },
            }
        )


class AiProviderTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        ser = AiProviderTestSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        draft = None
        if vd.get("mode") is not None:
            draft = {
                "mode": vd.get("mode"),
                "base_url": vd.get("base_url") or "",
                "model_name": vd.get("model_name") or "",
                "api_key": vd.get("api_key") or "",
                "use_saved_key": bool(vd.get("use_saved_key", True)),
            }
        try:
            result = test_user_provider(request.user, draft=draft)
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


class PendingActionsListView(APIView):
    """File d'attente Command Approval (actions IA en attente)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        from django.utils import timezone

        from apps.ai_assistant.models import PendingAction
        from apps.ai_assistant.services.redaction import redact_obj
        from apps.ai_assistant.tools.helpers import (
            action_command_preview,
            action_risk,
        )

        now = timezone.now()
        qs = PendingAction.objects.filter(
            owner=request.user,
            status=PendingAction.Status.PENDING,
            expires_at__gt=now,
        ).order_by("-created_at")[:50]
        items = [
            {
                "token": a.token,
                "tool_name": a.tool_name,
                "description": a.description,
                "params": redact_obj(a.params),
                "expires_at": a.expires_at.isoformat(),
                "created_at": a.created_at.isoformat(),
                "conversation_id": a.conversation_id,
                "risk": action_risk(a.tool_name, a.params),
                "command_preview": action_command_preview(a.tool_name, a.params),
            }
            for a in qs
        ]
        return Response({"success": True, "data": {"pending_actions": items, "count": len(items)}})
