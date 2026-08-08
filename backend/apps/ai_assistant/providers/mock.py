"""Provider mock conversationnel (fallback sans LLM) — actions panel d'abord."""
from __future__ import annotations

import json
import re
from uuid import uuid4

from apps.ai_assistant.providers import ChatMessage, ChatResult, ToolCallRequest, ToolSpec


class MockProvider:
    """Coach local : tools pour les demandes concrètes, chat sinon."""

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

        # Après tool(s) → réponse lisible (pas un dump JSON brut)
        if messages and messages[-1].role == "tool":
            return ChatResult(
                content=_synthesize_tools(messages),
                provider=self.name,
                model="mock-coach",
            )

        # Intentions d'action — AVANT le bavardage multi-tours
        intent = _detect_intent(last_user_l, messages)
        if intent:
            calls = _pack_calls(tool_names, intent["tools"])
            if calls:
                return ChatResult(
                    content=intent["say"],
                    tool_calls=calls,
                    provider=self.name,
                    model="mock-coach",
                )

        return ChatResult(
            content=_converse(last_user, prev_assistant, user_turns),
            provider=self.name,
            model="mock-coach",
        )


def _detect_intent(last_user_l: str, messages: list[ChatMessage]) -> dict | None:
    page_blob = " ".join(
        (m.content or "").lower()
        for m in messages
        if m.role == "system" and "page actuelle" in (m.content or "").lower()
    )

    wants_list = any(
        k in last_user_l
        for k in (
            "liste",
            "lister",
            "list ",
            "montre",
            "montrer",
            "affiche",
            "quels sont",
            "quelles sont",
            "mes app",
            "mes application",
            "mes site",
        )
    )
    mentions_python = "python" in last_user_l or "django" in last_user_l or "flask" in last_user_l
    mentions_node = "node" in last_user_l or "npm" in last_user_l
    mentions_apps = any(
        k in last_user_l for k in ("app", "application", "projet", "site", "service")
    )

    if wants_list and (mentions_python or mentions_node or mentions_apps or "python" in page_blob):
        return {
            "say": "Je liste tes applications sur le compte…",
            "tools": [("check_application_status", {})],
        }

    if any(k in last_user_l for k in ("statut", "status", "running", "qui tourne", "état")):
        return {
            "say": "Je vérifie le statut de tes apps…",
            "tools": [("check_application_status", {})],
        }

    if any(k in last_user_l for k in ("domaine", "domain", "dns")) and wants_list:
        return {
            "say": "Je regarde tes domaines…",
            "tools": [("get_deployment_context", {})],
        }

    page_auto = any(k in last_user_l for k in ("je suis sur", "page setup", "vérifie le statut"))
    if ("python" in page_blob or mentions_python) and (
        "log" in last_user_l or "statut" in last_user_l or page_auto
    ):
        return {
            "say": "Ok, je regarde le statut et les logs Python…",
            "tools": [
                ("check_application_status", {}),
                ("get_page_logs", {"runtime": "python", "lines": 100}),
                ("analyze_deployment_error", {"runtime": "python"}),
            ],
        }

    if ("node" in page_blob or mentions_node) and (
        "log" in last_user_l or "statut" in last_user_l or page_auto
    ):
        return {
            "say": "Ok, je regarde tes apps Node et les logs…",
            "tools": [
                ("check_application_status", {}),
                ("get_page_logs", {"runtime": "node", "lines": 100}),
            ],
        }

    if any(k in last_user_l for k in ("log", "erreur", "error", "failed", "échou", "traceback")):
        rt = _guess_runtime(last_user_l)
        return {
            "say": "Je récupère les logs pour comprendre l'erreur…",
            "tools": [
                ("get_deployment_logs", {"runtime": rt, "lines": 80}),
                ("analyze_deployment_error", {"runtime": rt}),
            ],
        }

    if "jail" in last_user_l or (
        "commande" in last_user_l and any(k in last_user_l for k in ("liste", "dispo", "autoris"))
    ):
        return {
            "say": "Voici le catalogue des commandes jail autorisées…",
            "tools": [("list_jail_commands", {})],
        }

    if any(k in last_user_l for k in ("contexte", "compte", "ce que j'ai", "ce que j ai")):
        return {
            "say": "Je regarde ce qui existe déjà sur ton compte…",
            "tools": [("get_deployment_context", {}), ("check_application_status", {})],
        }

    return None


def _synthesize_tools(messages: list[ChatMessage]) -> str:
    """Agrège les derniers résultats tool en texte utile."""
    tool_msgs: list[ChatMessage] = []
    for m in reversed(messages):
        if m.role != "tool":
            break
        tool_msgs.append(m)
    tool_msgs.reverse()

    parts: list[str] = []
    for m in tool_msgs:
        name = m.name or "outil"
        try:
            data = json.loads(m.content or "{}")
        except json.JSONDecodeError:
            data = {"raw": (m.content or "")[:800]}
        if not isinstance(data, dict):
            data = {"raw": str(data)[:800]}

        if name == "check_application_status":
            parts.append(_format_apps(data))
        elif name in {"get_deployment_context", "get_server_info"}:
            parts.append(_format_context(name, data))
        elif "log" in name or "analyze" in name:
            parts.append(_format_logs(name, data))
        else:
            ok = data.get("ok", True)
            err = data.get("error")
            if err:
                parts.append(f"**{name}** : erreur — {err}")
            else:
                snippet = json.dumps(data.get("data", data), ensure_ascii=False)[:900]
                parts.append(f"**{name}** (ok={ok}) :\n```json\n{snippet}\n```")

    body = "\n\n".join(p for p in parts if p) or "Aucune donnée retournée par les outils."
    return body + "\n\nTu veux les logs d'une app, un redémarrage, ou autre chose ?"


def _format_apps(data: dict) -> str:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    py = payload.get("python_apps") or []
    node = payload.get("node_apps") or []
    lines = ["Voici tes applications :", ""]
    lines.append(f"**Python** ({len(py)})")
    if not py:
        lines.append("- Aucune app Python sur ce compte.")
    else:
        for a in py:
            if not isinstance(a, dict):
                continue
            domain = a.get("domain") or "—"
            err = (a.get("last_error") or "").strip()
            extra = f" — ⚠ {err[:80]}" if err else ""
            lines.append(
                f"- `{a.get('name')}` — **{a.get('status')}** — port {a.get('port')} — "
                f"domaine {domain}{extra}"
            )
    lines.append("")
    lines.append(f"**Node.js** ({len(node)})")
    if not node:
        lines.append("- Aucune app Node sur ce compte.")
    else:
        for a in node:
            if not isinstance(a, dict):
                continue
            err = (a.get("last_error") or "").strip()
            extra = f" — ⚠ {err[:80]}" if err else ""
            lines.append(
                f"- `{a.get('name')}` — **{a.get('status')}** — port {a.get('port')}{extra}"
            )
    return "\n".join(lines)


def _format_context(name: str, data: dict) -> str:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    keys = ", ".join(sorted(str(k) for k in list(payload.keys())[:12])) if isinstance(payload, dict) else ""
    return f"**{name}** — champs : {keys or 'n/a'}."


def _format_logs(name: str, data: dict) -> str:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    text = ""
    if isinstance(payload, dict):
        text = str(payload.get("logs") or payload.get("excerpt") or payload.get("analysis") or "")
    if not text:
        text = json.dumps(payload, ensure_ascii=False)[:1200]
    return f"**{name}** :\n```\n{text[:1500]}\n```"


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

    if re.search(r"\b(bonjour|salut|hello|hey|coucou)\b", low) and len(low) < 40:
        return (
            "Salut ! Je suis **V-zone AI** (mode local).\n\n"
            "Demande concrète = j'agis tout de suite, par ex. :\n"
            "- *liste mes applications Python*\n"
            "- *montre le statut de mes apps*\n"
            "- *analyse mes logs*\n\n"
            "Qu'est-ce que tu veux faire ?"
        )

    if any(k in low for k in ("merci", "thanks", "nickel", "parfait", "super")):
        return "Avec plaisir. Tu veux enchaîner (logs, domaine, déploiement…) ?"

    if any(k in low for k in ("qui es-tu", "tu peux quoi", "que peux-tu", "tes capacités")):
        return (
            "Assistant V-zone (mode local sans LLM) : je liste apps/domaines, lis les logs, "
            "et propose des actions (restart, install) **après confirmation**.\n\n"
            "Essaie : *liste mes applications Python*."
        )

    if any(k in low for k in ("wsgi", "asgi", "passenger", "gunicorn", "uvicorn")):
        return (
            "- **WSGI** : Django classique (souvent `passenger_wsgi.py` / gunicorn).\n"
            "- **ASGI** : async (FastAPI, uvicorn).\n"
            "- Sur V-zone : app → port local → domaine en reverse-proxy.\n\n"
            "Tu configures Django ou FastAPI ?"
        )

    url = ""
    m = re.search(r"(https?://[^\s]+|git@[^\s]+)", text)
    if m:
        url = m.group(1)

    if url or any(k in low for k in ("django", "flask", "fastapi", "déploy", "deploy", "github")):
        return (
            "OK pour le déploiement"
            + (f" (`{url}`)" if url else "")
            + ". Dis-moi : runtime (Django/Node), domaine, besoin d'une base ? "
            "Ou *liste mes apps* si tu veux voir l'existant."
        )

    # Multi-tours : rester utile, pas "que préfères-tu ?" en boucle
    if len(user_turns) >= 2 and prev_assistant:
        return (
            f"Bien reçu : « {text[:240]} ».\n\n"
            "En mode local je suis meilleur sur les **actions panel**. "
            "Ex. *liste mes applications Python*, *statut*, *logs Python*."
        )

    return (
        f"Compris : « {text[:280]} ».\n\n"
        "Pour du concret tout de suite : *liste mes applications Python* "
        "ou *analyse mes logs*."
    )
