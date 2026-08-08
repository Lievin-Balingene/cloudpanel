"""Provider mock conversationnel (fallback sans LLM) — style chat multi-tours."""
from __future__ import annotations

import re
from uuid import uuid4

from apps.ai_assistant.providers import ChatMessage, ChatResult, ToolCallRequest, ToolSpec


class MockProvider:
    """Coach local : conversation naturelle + tools seulement si intention claire."""

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
        prev_assistant = ""
        user_turns: list[str] = []
        for m in messages:
            if m.role == "user" and m.content:
                user_turns.append(m.content)
            if m.role == "assistant" and m.content and not m.content.startswith("(outil"):
                prev_assistant = m.content
        if user_turns:
            last_user = user_turns[-1]
        last_user_l = last_user.lower()

        # Après un tool → synthèse conversationnelle
        if messages and messages[-1].role == "tool":
            tool_payload = messages[-1].content or "{}"
            name = messages[-1].name or "outil"
            return ChatResult(
                content=(
                    f"J'ai consulté **{name}**. Voici ce que j'en retiens :\n\n"
                    f"```json\n{tool_payload[:2200]}\n```\n\n"
                    "Tu veux que je t'explique ça simplement, que je propose une correction, "
                    "ou qu'on passe à l'étape suivante ?"
                ),
                provider=self.name,
                model="mock-coach",
            )

        # Intent tools (seulement si mots-clés d'action / diagnostic)
        action_hit = any(
            k in last_user_l
            for k in (
                "log",
                "erreur",
                "error",
                "failed",
                "échou",
                "statut",
                "status",
                "analyse",
                "diagnost",
                "redémar",
                "restart",
                "install",
                "npm",
                "pip",
                "jail",
                "commande",
                "pull",
                "déploy",
                "deploy",
                "clone",
            )
        )
        page_auto = any(k in last_user_l for k in ("je suis sur", "page setup", "vérifie le statut"))

        if action_hit or page_auto:
            page_blob = " ".join(
                (m.content or "").lower()
                for m in messages
                if m.role == "system" and "page actuelle" in (m.content or "").lower()
            )
            if ("python" in page_blob or "python" in last_user_l) and (
                "log" in last_user_l or "statut" in last_user_l or page_auto
            ):
                calls = _pack_calls(
                    tool_names,
                    [
                        ("check_application_status", {}),
                        ("get_page_logs", {"runtime": "python", "lines": 100}),
                        ("analyze_deployment_error", {"runtime": "python"}),
                    ],
                )
                if calls:
                    return ChatResult(
                        content="Ok, je regarde le statut et les logs Python…",
                        tool_calls=calls,
                        provider=self.name,
                        model="mock-coach",
                    )
            if ("node" in page_blob or "node" in last_user_l) and (
                "log" in last_user_l or "statut" in last_user_l or page_auto
            ):
                calls = _pack_calls(
                    tool_names,
                    [
                        ("check_application_status", {}),
                        ("get_page_logs", {"runtime": "node", "lines": 100}),
                    ],
                )
                if calls:
                    return ChatResult(
                        content="Ok, je regarde tes apps Node et les logs…",
                        tool_calls=calls,
                        provider=self.name,
                        model="mock-coach",
                    )
            if any(k in last_user_l for k in ("log", "erreur", "error", "failed", "échou")):
                rt = _guess_runtime(last_user_l)
                calls = _pack_calls(
                    tool_names,
                    [
                        ("get_deployment_logs", {"runtime": rt, "lines": 80}),
                        ("analyze_deployment_error", {"runtime": rt}),
                    ],
                )
                if calls:
                    return ChatResult(
                        content="Je récupère les logs pour comprendre l'erreur…",
                        tool_calls=calls,
                        provider=self.name,
                        model="mock-coach",
                    )
            if any(k in last_user_l for k in ("statut", "status", "running")):
                if "check_application_status" in tool_names:
                    return ChatResult(
                        content="Je vérifie ce qui tourne sur ton compte…",
                        tool_calls=[
                            ToolCallRequest(
                                id=str(uuid4()), name="check_application_status", arguments={}
                            )
                        ],
                        provider=self.name,
                        model="mock-coach",
                    )
            if any(k in last_user_l for k in ("django", "déploy", "deploy", "github", "git", "clone")):
                # Ne renvoie PLUS jamais une checklist figée : tools + suite conversationnelle
                calls = _pack_calls(
                    tool_names,
                    [("get_deployment_context", {})],
                )
                if calls and any(k in last_user_l for k in ("statut", "compte", "existant", "déjà", "contexte")):
                    return ChatResult(
                        content="Je regarde ce qui existe déjà sur ton compte…",
                        tool_calls=calls,
                        provider=self.name,
                        model="mock-coach",
                    )
                # Sinon conversation libre (pas de dump checklist)
                return ChatResult(
                    content=_converse(last_user, prev_assistant, user_turns),
                    provider=self.name,
                    model="mock-coach",
                )
            if "jail" in last_user_l or "commande" in last_user_l:
                if "list_jail_commands" in tool_names:
                    return ChatResult(
                        content="Voici le catalogue des commandes jail autorisées…",
                        tool_calls=[
                            ToolCallRequest(id=str(uuid4()), name="list_jail_commands", arguments={})
                        ],
                        provider=self.name,
                        model="mock-coach",
                    )

        # Conversation libre multi-tours
        return ChatResult(
            content=_converse(last_user, prev_assistant, user_turns),
            provider=self.name,
            model="mock-coach",
        )


def _pack_calls(tool_names: set[str], wanted: list[tuple[str, dict]]) -> list[ToolCallRequest]:
    out: list[ToolCallRequest] = []
    for name, args in wanted:
        if name in tool_names:
            out.append(ToolCallRequest(id=str(uuid4()), name=name, arguments=args))
    return out


def _guess_runtime(text: str) -> str:
    if "node" in text or "npm" in text:
        return "node"
    if "php" in text or "wordpress" in text or "wp" in text:
        return "php"
    return "python"


def _converse(last_user: str, prev_assistant: str, user_turns: list[str]) -> str:
    text = (last_user or "").strip()
    low = text.lower()

    if re.search(r"\b(bonjour|salut|hello|hey|coucou)\b", low):
        return (
            "Salut ! Je suis **V-zone AI** — on peut discuter librement comme avec ChatGPT, "
            "et j'ai aussi accès aux outils du panneau (logs, apps, git, jail contrôlé).\n\n"
            "Par exemple : *« explique-moi WSGI »*, *« aide-moi à déployer Django »*, "
            "*« analyse mes logs »*. Qu'est-ce que tu veux faire ?"
        )

    if any(k in low for k in ("merci", "thanks", "nickel", "parfait", "super")):
        return (
            "Avec plaisir 🙂 Dis-moi si tu veux enchaîner sur autre chose "
            "(logs, domaine, base, déploiement…)."
        )

    if any(k in low for k in ("qui es-tu", "tu peux quoi", "que peux-tu", "tes capacités", "aide")):
        return (
            "Je suis l'assistant IA intégré à V-zone. Je peux :\n\n"
            "1. **Discuter** — concepts, architecture, debug, bonnes pratiques\n"
            "2. **Diagnostiquer** — logs, statut apps, config domaine/DB\n"
            "3. **Agir** — après ta confirmation : install deps, restart, git pull, "
            "commandes jail whitelistées\n\n"
            "Pas de shell libre (sécurité). Qu'est-ce qui t'occupe en ce moment ?"
        )

    if any(k in low for k in ("wsgi", "asgi", "passenger", "gunicorn", "uvicorn")):
        return (
            "En bref :\n\n"
            "- **WSGI** : interface classique Python ↔ serveur web (Django souvent via "
            "`passenger_wsgi.py` / gunicorn).\n"
            "- **ASGI** : version async (FastAPI, Django async, uvicorn).\n"
            "- Sur V-zone, une app Python a un **port local** + un **domaine** qui reverse-proxy.\n\n"
            "Tu configures une app Django ou FastAPI ?"
        )

    if any(k in low for k in ("c'est quoi", "cest quoi", "explique", "comment marche", "différenc")):
        topic = text
        return (
            f"Bonne question. Voici une explication simple sur : « {topic[:120]} ».\n\n"
            "Dans le contexte V-zone, l'idée est toujours la même : ton code vit dans ton **home**, "
            "une app (Python/Node) écoute un port, nginx/OLS route ton domaine, "
            "et Git sert à mettre à jour le code.\n\n"
            "Tu veux que je détaille un point précis, ou qu'on regarde **ton** compte "
            "(apps / domaines) pour illustrer ?"
        )

    # Suites de conversation
    if len(user_turns) >= 2 and prev_assistant:
        return (
            f"Je te suis. Tu as dit : « {text[:240]} ».\n\n"
            "On peut continuer dans cette direction : je t'explique plus en détail, "
            "ou je regarde les données live du panel (statut / logs) si tu veux du concret.\n\n"
            "Que préfères-tu ?"
        )

    url = ""
    m = re.search(r"(https?://[^\s]+|git@[^\s]+)", text)
    if m:
        url = m.group(1)

    if url or any(k in low for k in ("django", "flask", "fastapi", "node", "wordpress")):
        return (
            "OK, parlons-en comme dans un vrai chat.\n\n"
            + (f"J'ai repéré `{url}`.\n\n" if url else "")
            + "Pas besoin d'une checklist figée : dis-moi juste **où tu en es** "
            "(repo prêt ? domaine ? erreur sous les yeux ?). "
            "On avance message par message."
        )

    return (
        f"Compris : « {text[:280]} ».\n\n"
        "Je t'écoute. Tu peux me parler normalement — concepts, plan, debug, ou "
        "me demander d'aller chercher statut/logs dans le panel. "
        "Qu'est-ce que tu veux obtenir comme prochain résultat ?"
    )
