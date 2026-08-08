"""Tools Kubernetes (aperçu cluster + apply/delete manifeste)."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, require_str, run_service


def _redact_manifest(manifest: str, *, max_len: int = 400) -> str:
    text = str(manifest or "")
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"… (+{len(text) - max_len} chars)"


@register_tool(
    name="get_k8s_overview",
    description="Aperçu Kubernetes (disponibilité kubectl / cluster). Accessible au client authentifié.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def get_k8s_overview(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    # Cluster souvent global ; on autorise tout utilisateur authentifié.
    _ = user

    def _run():
        from apps.kubernetes.services import overview_for

        return overview_for()

    return run_service(_run)


@register_tool(
    name="list_k8s_resources",
    description="Liste namespaces / pods / workloads Kubernetes (aperçu).",
    parameters={
        "type": "object",
        "properties": {"soft": {"type": "boolean"}},
        "additionalProperties": False,
    },
)
def list_k8s_resources(user: User, params: dict[str, Any]) -> dict[str, Any]:
    _ = user
    soft = bool(params.get("soft", True))

    def _run():
        from apps.kubernetes.services import list_resources

        data = list_resources(soft=soft)
        # Limite la taille de réponse
        if isinstance(data, dict):
            for key in ("pods", "workloads", "namespaces"):
                items = data.get(key)
                if isinstance(items, list) and len(items) > 100:
                    data[key] = items[:100]
                    data[f"{key}_truncated"] = True
        return data

    return run_service(_run)


@register_tool(
    name="apply_k8s_manifest",
    description="Applique un manifeste Kubernetes YAML (confirmation requise). Le manifeste complet n'est pas renvoyé.",
    parameters={
        "type": "object",
        "properties": {
            "manifest": {"type": "string"},
            "namespace": {"type": "string"},
        },
        "required": ["manifest"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def apply_k8s_manifest(user: User, params: dict[str, Any]) -> dict[str, Any]:
    _ = user
    from apps.kubernetes.services import apply_manifest

    manifest = str(params.get("manifest") or "")
    if not manifest.strip():
        return err("manifest requis")
    namespace = require_str(params, "namespace", max_len=63)

    def _run():
        result = apply_manifest(manifest, namespace=namespace)
        out = result if isinstance(result, dict) else {"result": result}
        out["manifest_preview"] = _redact_manifest(manifest)
        out.pop("manifest", None)
        return out

    return run_service(_run)


@register_tool(
    name="delete_k8s_manifest",
    description="Supprime des ressources Kubernetes via manifeste YAML (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "manifest": {"type": "string"},
            "namespace": {"type": "string"},
        },
        "required": ["manifest"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_k8s_manifest(user: User, params: dict[str, Any]) -> dict[str, Any]:
    _ = user
    from apps.kubernetes.services import delete_manifest

    manifest = str(params.get("manifest") or "")
    if not manifest.strip():
        return err("manifest requis")
    namespace = require_str(params, "namespace", max_len=63)

    def _run():
        result = delete_manifest(manifest, namespace=namespace)
        out = result if isinstance(result, dict) else {"result": result}
        out["manifest_preview"] = _redact_manifest(manifest)
        out.pop("manifest", None)
        return out

    return run_service(_run)
