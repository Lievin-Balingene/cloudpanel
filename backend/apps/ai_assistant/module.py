from __future__ import annotations

from apps.core.module_registry import ModuleMeta, registry

registry.register(
    ModuleMeta(
        name="ai_assistant",
        label="AI Deployment Assistant",
        version="0.35.27",
        description=(
            "Assistant IA conversationnel (style ChatGPT) : dialogue multi-tours, "
            "tools contrôlés, contexte page, jail whitelist."
        ),
        dependencies=("core", "accounts", "git_deploy", "python_apps", "node_apps", "domains"),
        api_prefix="ai",
        permissions=("ai_assistant.view", "ai_assistant.use", "ai_assistant.manage"),
        enabled_by_default=True,
    )
)
