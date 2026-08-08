"""Provider mock / coach déterministe (tests + fallback sans LLM)."""
from __future__ import annotations

import re
from uuid import uuid4

from apps.ai_assistant.providers import ChatMessage, ChatResult, ToolCallRequest, ToolSpec


class MockProvider:
    """Assistant guidé sans dépendance réseau — tool-calls heuristiques sûres."""

    name = "mock"

    def is_available(self) -> bool:
        return True

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        del temperature
        tool_names = {t.name for t in (tools or [])}
        last_user = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user = (m.content or "").lower()
                break

        # Si le dernier message est un résultat d'outil → synthèse
        if messages and messages[-1].role == "tool":
            tool_payload = messages[-1].content or "{}"
            return ChatResult(
                content=(
                    "**Analyse (mode local)**\n\n"
                    f"Résultat outil `{messages[-1].name}` reçu.\n\n"
                    "```json\n"
                    f"{tool_payload[:2500]}\n"
                    "```\n\n"
                    "Indiquez la prochaine étape (runtime, domaine, base, variables d'env) "
                    "ou demandez un diagnostic plus précis."
                ),
                provider=self.name,
                model="mock-coach",
            )

        # Intent → tool calls lecture uniquement
        if any(k in last_user for k in ("log", "erreur", "error", "failed", "échou")):
            calls: list[ToolCallRequest] = []
            if "get_deployment_logs" in tool_names:
                calls.append(
                    ToolCallRequest(
                        id=str(uuid4()),
                        name="get_deployment_logs",
                        arguments={"runtime": _guess_runtime(last_user), "lines": 80},
                    )
                )
            if "analyze_deployment_error" in tool_names:
                calls.append(
                    ToolCallRequest(
                        id=str(uuid4()),
                        name="analyze_deployment_error",
                        arguments={"runtime": _guess_runtime(last_user)},
                    )
                )
            if calls:
                return ChatResult(
                    content="Je récupère les logs et j'analyse l'erreur…",
                    tool_calls=calls,
                    provider=self.name,
                    model="mock-coach",
                )

        if any(k in last_user for k in ("statut", "status", "running", "écoute")):
            if "check_application_status" in tool_names:
                return ChatResult(
                    content="Vérification du statut des applications…",
                    tool_calls=[
                        ToolCallRequest(
                            id=str(uuid4()),
                            name="check_application_status",
                            arguments={},
                        )
                    ],
                    provider=self.name,
                    model="mock-coach",
                )

        if any(k in last_user for k in ("django", "déploy", "deploy", "github", "git")):
            calls = []
            if "get_deployment_context" in tool_names:
                calls.append(
                    ToolCallRequest(
                        id=str(uuid4()),
                        name="get_deployment_context",
                        arguments={},
                    )
                )
            if "get_server_info" in tool_names:
                calls.append(
                    ToolCallRequest(id=str(uuid4()), name="get_server_info", arguments={})
                )
            if calls:
                return ChatResult(
                    content="Je charge le contexte de votre compte et les infos serveur…",
                    tool_calls=calls,
                    provider=self.name,
                    model="mock-coach",
                )

        if "python" in last_user and "check_python_version" in tool_names:
            return ChatResult(
                content="Contrôle des runtimes Python disponibles…",
                tool_calls=[
                    ToolCallRequest(id=str(uuid4()), name="check_python_version", arguments={})
                ],
                provider=self.name,
                model="mock-coach",
            )

        if "node" in last_user and "check_node_version" in tool_names:
            return ChatResult(
                content="Contrôle des runtimes Node.js…",
                tool_calls=[
                    ToolCallRequest(id=str(uuid4()), name="check_node_version", arguments={})
                ],
                provider=self.name,
                model="mock-coach",
            )

        return ChatResult(
            content=_welcome_guide(last_user),
            provider=self.name,
            model="mock-coach",
        )


def _guess_runtime(text: str) -> str:
    if "node" in text or "npm" in text:
        return "node"
    if "php" in text or "wordpress" in text or "wp" in text:
        return "php"
    return "python"


def _welcome_guide(last_user: str) -> str:
    url = ""
    m = re.search(r"(https?://[^\s]+|git@[^\s]+)", last_user or "")
    if m:
        url = m.group(1)
    lines = [
        "**V-zone AI Deployment Assistant** (mode local / sans LLM distant)",
        "",
        "Je peux vous guider pour déployer une app (Django, Node, PHP/WordPress) "
        "en réutilisant les outils du panneau — **sans shell libre**.",
        "",
        "Pour un déploiement GitHub → Django, j'ai besoin de :",
        "1. URL du dépôt" + (f" *(détectée : `{url}`)*" if url else ""),
        "2. Branche (ex. `main`)",
        "3. Version Python",
        "4. Domaine cible",
        "5. Base de données (oui/non)",
        "6. Variables d'environnement (noms seulement, pas les secrets)",
        "7. Commande d'install (`pip install -r requirements.txt`)",
        "8. Point d'entrée (module WSGI/ASGI)",
        "",
        "Décrivez votre projet ou demandez : *« analyse mes logs Python »*, "
        "*« statut de mes apps »*, *« versions disponibles »*.",
    ]
    return "\n".join(lines)
