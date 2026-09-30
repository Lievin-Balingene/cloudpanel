"""Résolution du provider LLM : serveur (défaut) ou BYOK client."""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import User
from apps.ai_assistant.models import UserAiProviderSettings
from apps.ai_assistant.providers import LLMProvider, get_provider
from apps.ai_assistant.providers.mock import MockProvider
from apps.ai_assistant.providers.ollama import OllamaProvider
from apps.ai_assistant.providers.openai_compat import OpenAICompatProvider
from apps.core.exceptions import VZoneAPIException
from apps.databases.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)


def byok_feature_enabled() -> bool:
    return bool(getattr(settings, "VZONE_AI_BYOK_ENABLED", True))


def get_or_create_settings(user: User) -> UserAiProviderSettings:
    obj, _ = UserAiProviderSettings.objects.get_or_create(owner=user)
    return obj


def settings_public_dict(obj: UserAiProviderSettings | None) -> dict[str, Any]:
    if obj is None:
        return {
            "mode": UserAiProviderSettings.Mode.SERVER,
            "base_url": "",
            "model_name": "",
            "has_api_key": False,
            "enabled": True,
            "last_test_ok": None,
            "last_test_message": "",
            "last_tested_at": None,
            "is_byok_active": False,
        }
    return {
        "mode": obj.mode,
        "base_url": obj.base_url or "",
        "model_name": obj.model_name or "",
        "has_api_key": bool(obj.api_key_encrypted),
        "enabled": bool(obj.enabled),
        "last_test_ok": obj.last_test_ok,
        "last_test_message": obj.last_test_message or "",
        "last_tested_at": obj.last_tested_at.isoformat() if obj.last_tested_at else None,
        "is_byok_active": obj.is_byok_active,
    }


def _byok_timeout() -> int:
    return int(getattr(settings, "VZONE_AI_BYOK_TIMEOUT_SEC", 30) or 30)


# Anciens IDs Google retirés / bloqués aux nouveaux comptes → Flash 3.5 actuel
GEMINI_MODEL_ALIASES: dict[str, str] = {
    "gemini-1.5-flash": "gemini-3.5-flash",
    "gemini-1.5-flash-latest": "gemini-3.5-flash",
    "gemini-1.5-flash-001": "gemini-3.5-flash",
    "gemini-1.5-flash-002": "gemini-3.5-flash",
    "gemini-1.5-pro": "gemini-3.5-flash",
    "gemini-1.5-pro-latest": "gemini-3.5-flash",
    "gemini-2.0-flash": "gemini-3.5-flash",
    "gemini-2.0-flash-001": "gemini-3.5-flash",
    "gemini-2.0-flash-lite": "gemini-3.5-flash-lite",
    "gemini-2.5-flash": "gemini-3.5-flash",
    "gemini-2.5-flash-lite": "gemini-3.5-flash-lite",
    "gemini-2.5-pro": "gemini-3.5-flash",
    "gemini-pro": "gemini-3.5-flash",
}

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


def normalize_gemini_model(model: str) -> str:
    """Remappe les modèles Gemini dépréciés vers un ID encore servi."""
    name = (model or "").strip()
    if not name:
        return DEFAULT_GEMINI_MODEL
    # Accepte "models/gemini-…" venant de l'API native
    if name.startswith("models/"):
        name = name[len("models/") :]
    low = name.lower()
    return GEMINI_MODEL_ALIASES.get(low, name)


def normalize_openai_compat_base_url(url: str) -> str:
    """
    Normalise la base OpenAI-compat (…/v1) sans casser Gemini / OpenRouter.

    Gemini OpenAI-compat :
      https://generativelanguage.googleapis.com/v1beta/openai
      → …/chat/completions  (PAS …/openai/v1/chat/completions)
    """
    base = (url or "").rstrip("/")
    if not base:
        return base
    low = base.lower()
    # Déjà un endpoint OpenAI-compat complet
    if low.endswith("/v1") or low.endswith("/openai") or "/openai/v1" in low:
        return base
    # Chemins déjà versionnés (…/v1beta/…, …/v1alpha/…) sans /openai
    if "/v1beta" in low or "/v1alpha" in low:
        if "generativelanguage.googleapis.com" in low and not low.endswith("/openai"):
            return f"{base}/openai"
        return base
    # OpenRouter, Groq, OpenAI classiques
    if "/v1/" in low:
        return base
    return f"{base}/v1"


def build_byok_provider(obj: UserAiProviderSettings) -> LLMProvider:
    """Construit un provider à partir des réglages BYOK (sans fallback serveur)."""
    from apps.ai_assistant.services.url_safety import validate_byok_url

    url = validate_byok_url(obj.base_url)
    model = (obj.model_name or "").strip()
    api_key = decrypt_secret(obj.api_key_encrypted) or ""
    timeout = _byok_timeout()

    if obj.mode == UserAiProviderSettings.Mode.OLLAMA:
        if not model:
            model = "llama3.2"
        return OllamaProvider(
            base_url=url,
            model=model,
            timeout=timeout,
            use_global_circuit=False,
        )
    if obj.mode == UserAiProviderSettings.Mode.OPENAI_COMPAT:
        if not model:
            model = "gpt-4o-mini"
        url = normalize_openai_compat_base_url(url)
        if "generativelanguage.googleapis.com" in url.lower():
            model = normalize_gemini_model(model)
        if not api_key:
            raise VZoneAPIException(
                detail="Clé API requise pour le mode OpenAI-compatible (Gemini, OpenAI…).",
                code="byok_key_required",
                status_code=400,
            )
        return OpenAICompatProvider(
            base_url=url,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )
    raise VZoneAPIException(
        detail="Mode BYOK invalide.",
        code="byok_mode_invalid",
        status_code=400,
    )


def get_provider_for_user(user: User | None) -> LLMProvider:
    """Provider effectif pour un utilisateur (BYOK si actif, sinon serveur)."""
    if user is None or not byok_feature_enabled():
        return get_provider()
    try:
        obj = UserAiProviderSettings.objects.filter(owner=user).first()
    except Exception:  # noqa: BLE001
        return get_provider()
    if obj is None or not obj.is_byok_active:
        return get_provider()
    try:
        return build_byok_provider(obj)
    except VZoneAPIException:
        logger.warning("BYOK invalide pour user=%s — fallback serveur", getattr(user, "pk", "?"))
        return get_provider()
    except Exception:  # noqa: BLE001
        logger.exception("BYOK build failed user=%s", getattr(user, "pk", "?"))
        return get_provider()


def provider_source_for_user(user: User | None) -> str:
    if user is None or not byok_feature_enabled():
        return "server"
    obj = UserAiProviderSettings.objects.filter(owner=user).first()
    if obj and obj.is_byok_active:
        return "byok"
    return "server"


def update_user_provider_settings(
    user: User,
    *,
    mode: str,
    base_url: str = "",
    model_name: str = "",
    api_key: str | None = None,
    clear_api_key: bool = False,
    enabled: bool = True,
) -> UserAiProviderSettings:
    if not byok_feature_enabled():
        raise VZoneAPIException(
            detail="BYOK désactivé par l'administrateur (VZONE_AI_BYOK_ENABLED=false).",
            code="byok_disabled",
            status_code=403,
        )
    from apps.ai_assistant.services.url_safety import validate_byok_url

    mode = (mode or UserAiProviderSettings.Mode.SERVER).strip().lower()
    valid = {c.value for c in UserAiProviderSettings.Mode}
    if mode not in valid:
        raise VZoneAPIException(
            detail=f"Mode invalide. Choix: {', '.join(sorted(valid))}",
            code="byok_mode_invalid",
            status_code=400,
        )

    obj = get_or_create_settings(user)
    obj.mode = mode
    obj.enabled = bool(enabled)
    obj.model_name = (model_name or "").strip()[:128]

    if mode == UserAiProviderSettings.Mode.SERVER:
        obj.base_url = ""
        # On garde éventuellement la clé pour réactivation ultérieure
    else:
        obj.base_url = validate_byok_url(base_url)
        if not obj.model_name:
            obj.model_name = (
                "llama3.2" if mode == UserAiProviderSettings.Mode.OLLAMA else "gpt-4o-mini"
            )

    if clear_api_key:
        obj.api_key_encrypted = ""
    elif api_key is not None:
        key = api_key.strip()
        if key:
            if len(key) > 2048:
                raise VZoneAPIException(
                    detail="Clé API trop longue.",
                    code="byok_key_too_long",
                    status_code=400,
                )
            obj.api_key_encrypted = encrypt_secret(key)
        # api_key="" sans clear → ne pas écraser (garder l'existante)

    obj.save()
    return obj


def reset_user_provider_settings(user: User) -> UserAiProviderSettings:
    obj = get_or_create_settings(user)
    obj.mode = UserAiProviderSettings.Mode.SERVER
    obj.base_url = ""
    obj.api_key_encrypted = ""
    obj.model_name = ""
    obj.enabled = True
    obj.last_test_ok = None
    obj.last_test_message = ""
    obj.last_tested_at = None
    obj.save()
    return obj


def test_user_provider(user: User, *, draft: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Teste la connectivité du provider BYOK.
    Si draft fourni, teste sans persister (mode/url/model/api_key).
    """
    if not byok_feature_enabled():
        raise VZoneAPIException(
            detail="BYOK désactivé.",
            code="byok_disabled",
            status_code=403,
        )

    if draft is not None:
        mode = str(draft.get("mode") or "").strip().lower()
        if mode in {"", UserAiProviderSettings.Mode.SERVER}:
            provider = get_provider()
            ok = bool(provider.is_available()) or isinstance(provider, MockProvider)
            return {
                "ok": ok,
                "provider": getattr(provider, "name", "unknown"),
                "model": getattr(provider, "model", "") or "",
                "message": "Provider serveur OK" if ok else "Provider serveur indisponible",
                "models": getattr(provider, "list_models", lambda: [])(),
            }
        tmp = UserAiProviderSettings(
            owner=user,
            mode=mode,
            base_url=str(draft.get("base_url") or ""),
            model_name=str(draft.get("model_name") or ""),
            enabled=True,
        )
        key = draft.get("api_key")
        if key:
            tmp.api_key_encrypted = encrypt_secret(str(key).strip())
        elif draft.get("use_saved_key"):
            saved = UserAiProviderSettings.objects.filter(owner=user).first()
            if saved:
                tmp.api_key_encrypted = saved.api_key_encrypted
        provider = build_byok_provider(tmp)
    else:
        obj = get_or_create_settings(user)
        if not obj.is_byok_active:
            provider = get_provider()
        else:
            provider = build_byok_provider(obj)

    models_list: list[str] = []
    try:
        if hasattr(provider, "list_models"):
            models_list = list(provider.list_models() or [])
        available = bool(provider.is_available())
        if not available and isinstance(provider, MockProvider):
            available = True
        # Smoke chat court pour OpenAI-compat (is_available = URL seule)
        if available and getattr(provider, "name", "") == "openai_compat":
            from apps.ai_assistant.providers import ChatMessage

            result = provider.chat(
                [ChatMessage(role="user", content="Réponds uniquement: OK")],
                tools=None,
                temperature=0,
            )
            available = bool((result.content or "").strip() or True)
        message = "Connexion OK"
        if models_list:
            message = f"OK — {len(models_list)} modèle(s)"
        ok = available
    except Exception as exc:  # noqa: BLE001
        ok = False
        message = str(exc)[:240]

    # Persiste le résultat si on teste la config sauvegardée
    if draft is None:
        obj = get_or_create_settings(user)
        obj.last_test_ok = ok
        obj.last_test_message = message[:255]
        obj.last_tested_at = timezone.now()
        obj.save(update_fields=["last_test_ok", "last_test_message", "last_tested_at", "updated_at"])

    return {
        "ok": ok,
        "provider": getattr(provider, "name", "unknown"),
        "model": getattr(provider, "model", "") or "",
        "message": message,
        "models": models_list[:50],
    }
