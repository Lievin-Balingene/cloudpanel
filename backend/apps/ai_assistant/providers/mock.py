"""Provider mock conversationnel (fallback sans LLM) — actions panel d'abord."""
from __future__ import annotations

import json
import re
from typing import Any
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

        # Après tool(s) → éventuellement enchaîner stop/start/restart, sinon synthèse
        if messages and messages[-1].role == "tool":
            follow = _lifecycle_after_tools(messages, tool_names, last_user_l)
            if follow is not None:
                return follow
            return ChatResult(
                content=_synthesize_tools(messages),
                provider=self.name,
                model="mock-coach",
            )

        # Intentions d'action — AVANT le bavardage multi-tours
        intent = _detect_intent(last_user_l, messages, tool_names)
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


def _lifecycle_verb(text: str) -> str | None:
    """Retourne stop|start|restart selon l'intention utilisateur (mots entiers)."""
    import unicodedata

    raw = (text or "").lower().strip()
    # Normalise accents : démarrer → demarrer (évite les faux positifs substring)
    t = "".join(
        c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn"
    )

    # Ordre critique : restart / start AVANT stop (sinon "arret" peut polluer)
    if re.search(r"\b(re\s*-?\s*start|redemarr\w*|relance\w*|reboot\w*)\b", t):
        return "restart"
    if re.search(
        r"\b(start\w*|demarr\w*|lancer\w*|lance\w*|allum\w*|reactiv\w*|en\s+marche)\b",
        t,
    ):
        return "start"
    if re.search(
        r"\b(stop\w*|arret\w*|eteign\w*|eteint\w*|kill\w*|shutdown\w*|coup(er|e)\w*)\b",
        t,
    ):
        return "stop"
    return None


def _infer_app_id_from_history(messages: list[ChatMessage], last_user_l: str) -> int | None:
    """Si l'utilisateur dit « cette app » / démarre après un stop, reprend le dernier id."""
    vague = any(
        k in last_user_l
        for k in (
            "cette",
            "cet ",
            "la meme",
            "la même",
            "la-meme",
            "pareil",
            "encore",
            "remets",
            "application",
            "app",
        )
    )
    if not vague:
        return None
    # last_app dans le contexte système
    for m in messages:
        if m.role != "system":
            continue
        found = re.search(r'"last_app"\s*:\s*\{[^}]*"id"\s*:\s*(\d+)', m.content or "")
        if found:
            return int(found.group(1))
    for m in reversed(messages):
        content = m.content or ""
        for pat in (
            r"\(id\s+(\d+)\)",
            r"\bid\s*[:=]?\s*(\d+)\b",
            r"\bapp\s*[#:]?\s*(\d+)\b",
        ):
            hit = re.search(pat, content, re.IGNORECASE)
            if hit:
                return int(hit.group(1))
        if m.role == "tool" and (m.name or "") in {
            "stop_application",
            "start_application",
            "restart_application",
            "check_application_status",
        }:
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                if data.get("app_id"):
                    try:
                        return int(data["app_id"])
                    except (TypeError, ValueError):
                        pass
                payload = data.get("data") if isinstance(data.get("data"), dict) else data
                if isinstance(payload, dict) and payload.get("app_id"):
                    try:
                        return int(payload["app_id"])
                    except (TypeError, ValueError):
                        pass
    return None


def _extract_app_id(text: str) -> int | None:
    m = re.search(r"\b(?:id\s*[:=]?\s*|#\s*|app\s+)(\d{1,9})\b", text.lower())
    if m:
        return int(m.group(1))
    m2 = re.search(r"\b(\d{1,9})\b", text)
    # Evite de prendre un port / année au hasard : seulement si "app" voisin
    if m2 and any(k in text.lower() for k in ("app", "application", "id")):
        return int(m2.group(1))
    return None


def _detect_intent(
    last_user_l: str,
    messages: list[ChatMessage],
    tool_names: set[str],
) -> dict | None:
    page_blob = " ".join(
        (m.content or "").lower()
        for m in messages
        if m.role == "system" and "page actuelle" in (m.content or "").lower()
    )

    lifecycle = _lifecycle_verb(last_user_l)
    if lifecycle:
        runtime = _guess_runtime(last_user_l + " " + page_blob)
        app_id = _extract_app_id(last_user_l) or _infer_app_id_from_history(
            messages, last_user_l
        )
        tool_map = {
            "stop": "stop_application",
            "start": "start_application",
            "restart": "restart_application",
        }
        tool = tool_map[lifecycle]
        labels = {"stop": "arrêt", "start": "démarrage", "restart": "redémarrage"}
        if app_id and tool in tool_names:
            return {
                "say": f"Je prépare le {labels[lifecycle]} de l'app #{app_id} — confirmation requise…",
                "tools": [(tool, {"runtime": runtime if runtime in {"python", "node"} else "python", "app_id": app_id})],
            }
        return {
            "say": f"Je regarde tes apps pour préparer le {labels[lifecycle]}…",
            "tools": [("check_application_status", {})],
        }

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

    # —— Panneau client (lecture / actions fréquentes) ——
    if any(k in last_user_l for k in ("vue d'ensemble", "overview", "mon compte", "espace disque", "quota")):
        return {"say": "Je charge la vue d'ensemble du compte…", "tools": [("get_account_overview", {})]}
    if any(k in last_user_l for k in ("mon package", "mon forfait", "limites du package")):
        return {"say": "Je regarde ton package…", "tools": [("get_my_package", {})]}
    if any(k in last_user_l for k in ("2fa", "sécurité", "securite")) and "mot de passe" not in last_user_l:
        return {"say": "Je consulte le statut sécurité (lecture)…", "tools": [("get_security_status", {})]}

    if wants_list and any(k in last_user_l for k in ("domaine", "domain")):
        return {"say": "Je liste tes domaines…", "tools": [("list_domains", {})]}
    if any(k in last_user_l for k in ("ssl", "let's encrypt", "letsencrypt", "certificat")):
        if any(k in last_user_l for k in ("émet", "emet", "émettre", "emettre", "installer", "créer", "creer")):
            return {"say": "Je liste les domaines pour préparer le SSL…", "tools": [("list_domains", {})]}
        return {"say": "Je liste tes domaines / SSL…", "tools": [("list_domains", {})]}

    if wants_list and any(k in last_user_l for k in ("base", "database", "mysql", "postgres", "bdd")):
        return {"say": "Je liste tes bases de données…", "tools": [("list_databases", {})]}
    if any(k in last_user_l for k in ("crée une base", "creer une base", "nouvelle base", "create database")):
        return {"say": "Dis-moi le nom et le moteur (mysql/postgresql) — ou confirme après liste…", "tools": [("list_databases", {})]}

    if wants_list and any(k in last_user_l for k in ("cron", "tâche planif", "tache planif", "crontab")):
        return {"say": "Je liste tes tâches cron…", "tools": [("list_cron_jobs", {})]}
    if any(k in last_user_l for k in ("wordpress", "wp ")) or (wants_list and "wp" in last_user_l):
        return {"say": "Je liste tes sites WordPress…", "tools": [("list_wordpress_sites", {})]}

    if any(k in last_user_l for k in ("fichier", "dossier", "répertoire", "repertoire", "file manager")):
        path = ""
        m = re.search(r"(?:dans|path|chemin)\s+[«\"]?([^\s»\"]+)", last_user_l)
        if m:
            path = m.group(1)
        if any(k in last_user_l for k in ("cherche", "search", "trouve")):
            q = last_user_l.split("cherche")[-1].strip()[:80] if "cherche" in last_user_l else ""
            return {
                "say": "Je cherche dans tes fichiers…",
                "tools": [("search_account_files", {"query": q or "*", "path": path or ""})],
            }
        return {
            "say": "Je liste le contenu du home…",
            "tools": [("list_files", {"path": path or ""})],
        }

    if wants_list and "ftp" in last_user_l:
        return {"say": "Je liste tes comptes FTP…", "tools": [("list_ftp_accounts", {})]}
    if wants_list and any(k in last_user_l for k in ("backup", "sauvegarde")):
        return {"say": "Je liste tes sauvegardes…", "tools": [("list_backups", {})]}
    if any(k in last_user_l for k in ("lance une sauvegarde", "créer un backup", "creer un backup", "faire un backup")):
        return {
            "say": "Je prépare une sauvegarde complète — confirmation requise…",
            "tools": [("create_backup", {"backup_type": "full"})],
        }

    if wants_list and any(k in last_user_l for k in ("mail", "email", "boîte", "boite", "mailbox")):
        return {"say": "Je liste tes boîtes mail…", "tools": [("list_mailboxes", {})]}
    if wants_list and any(k in last_user_l for k in ("dns", "zone dns", "enregistrement")):
        return {"say": "Je liste tes zones DNS…", "tools": [("list_dns_zones", {})]}
    if wants_list and "php" in last_user_l:
        return {
            "say": "Je regarde les versions / sélecteurs PHP…",
            "tools": [("list_php_versions", {}), ("list_php_selectors", {})],
        }
    if wants_list and any(k in last_user_l for k in ("git", "dépôt", "depot", "repo")):
        return {"say": "Je liste tes dépôts Git…", "tools": [("list_git_repos", {})]}
    if wants_list and any(k in last_user_l for k in ("docker", "conteneur", "container")):
        return {"say": "Je liste tes conteneurs Docker…", "tools": [("list_docker_containers", {})]}
    if any(k in last_user_l for k in ("kubernetes", "k8s", "kubectl")):
        return {"say": "Vue Kubernetes…", "tools": [("get_k8s_overview", {})]}

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
            "tools": [
                ("get_account_overview", {}),
                ("get_deployment_context", {}),
                ("check_application_status", {}),
            ],
        }

    return None


def _apps_from_tool_payload(data: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict):
        return [], []
    py = [a for a in (payload.get("python_apps") or []) if isinstance(a, dict)]
    node = [a for a in (payload.get("node_apps") or []) if isinstance(a, dict)]
    return py, node


def _lifecycle_after_tools(
    messages: list[ChatMessage],
    tool_names: set[str],
    last_user_l: str,
) -> ChatResult | None:
    action = _lifecycle_verb(last_user_l)
    if not action:
        return None

    # Ne pas re-déclencher si on vient déjà d'un stop/start/restart
    for m in reversed(messages):
        if m.role != "tool":
            break
        if (m.name or "") in {"stop_application", "start_application", "restart_application"}:
            return None

    py_apps: list[dict] = []
    node_apps: list[dict] = []
    for m in reversed(messages):
        if m.role != "tool":
            break
        if (m.name or "") != "check_application_status":
            continue
        try:
            data = json.loads(m.content or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            py_apps, node_apps = _apps_from_tool_payload(data)
            break

    runtime = _guess_runtime(last_user_l)
    pool = py_apps if runtime != "node" else node_apps
    if runtime == "python" and not pool and node_apps and "python" not in last_user_l:
        # fallback si l'utilisateur dit juste "cette application"
        pool = py_apps or node_apps
        if not py_apps and node_apps:
            runtime = "node"
    if "cette" in last_user_l or "cet " in last_user_l:
        # Préfère les apps running pour stop, stopped pour start
        pass

    app_id = _extract_app_id(last_user_l) or _infer_app_id_from_history(messages, last_user_l)
    chosen: dict | None = None
    if app_id:
        for a in pool or (py_apps + node_apps):
            if int(a.get("id") or 0) == app_id:
                chosen = a
                if a in node_apps:
                    runtime = "node"
                elif a in py_apps:
                    runtime = "python"
                break
        # Id connu (ex. après un stop) même si pas encore dans le pool filtré
        if chosen is None and app_id and tool_map_name_for_action(action) in tool_names:
            runtime = runtime if runtime in {"python", "node"} else "python"
            return ChatResult(
                content=(
                    f"Je prépare l'action pour **{_action_label(action)}** l'app "
                    f"#{app_id} ({runtime}). Clique **Exécuter** pour confirmer."
                ),
                tool_calls=[
                    ToolCallRequest(
                        id=str(uuid4()),
                        name=tool_map_name_for_action(action),
                        arguments={"runtime": runtime, "app_id": app_id},
                    )
                ],
                provider="mock",
                model="mock-coach",
            )

    if chosen is None:
        candidates = list(pool or [])
        if action == "stop":
            candidates = [
                a
                for a in candidates
                if str(a.get("status") or "").lower() in {"running", "error", "active"}
            ] or candidates
        elif action == "start":
            # Inclut aussi les apps juste stoppées / en erreur
            candidates = [
                a
                for a in candidates
                if str(a.get("status") or "").lower()
                in {"stopped", "error", "pending", "failed", "exited"}
            ] or candidates
        # Match par nom dans le message
        for a in candidates:
            name = str(a.get("name") or "").lower()
            if name and name in last_user_l:
                chosen = a
                break
        if chosen is None and len(candidates) == 1:
            chosen = candidates[0]
        elif chosen is None and len(candidates) > 1:
            # Pour start/stop : préfère la plus récemment mise à jour si une seule runtime
            lines = [_format_apps({"data": {"python_apps": py_apps, "node_apps": node_apps}})]
            lines.append("")
            lines.append(
                f"Plusieurs apps trouvées. Dis-moi laquelle {_action_label(action)} "
                f"avec son **id** (ex. `{action} app {candidates[0].get('id')}`)."
            )
            return ChatResult(
                content="\n".join(lines),
                provider="mock",
                model="mock-coach",
            )
        elif chosen is None:
            return ChatResult(
                content=(
                    _format_apps({"data": {"python_apps": py_apps, "node_apps": node_apps}})
                    + "\n\nAucune app cible pour cette action. "
                    "Précise un **id** (ex. `démarre app 7`)."
                ),
                provider="mock",
                model="mock-coach",
            )

    tool = tool_map_name_for_action(action)
    if tool not in tool_names or not chosen:
        return None
    aid = int(chosen.get("id") or 0)
    name = str(chosen.get("name") or f"#{aid}")
    return ChatResult(
        content=(
            f"Je prépare l'action pour **{_action_label(action)}** `{name}` "
            f"(id {aid}, {runtime}). Clique **Exécuter** pour confirmer."
        ),
        tool_calls=[
            ToolCallRequest(
                id=str(uuid4()),
                name=tool,
                arguments={
                    "runtime": runtime if runtime in {"python", "node"} else "python",
                    "app_id": aid,
                },
            )
        ],
        provider="mock",
        model="mock-coach",
    )


def tool_map_name_for_action(action: str) -> str:
    return {
        "stop": "stop_application",
        "start": "start_application",
        "restart": "restart_application",
    }[action]


def _action_label(action: str) -> str:
    return {"stop": "arrêter", "start": "démarrer", "restart": "redémarrer"}.get(
        action, action
    )


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

        if data.get("pending_confirmation"):
            parts.append(
                f"Action **`{name}`** en attente de confirmation dans le panneau "
                f"(bouton **Exécuter**)."
            )
            continue

        if name == "check_application_status":
            parts.append(_format_apps(data))
        elif name in {"stop_application", "start_application", "restart_application"}:
            payload = data.get("data") if isinstance(data.get("data"), dict) else data
            if data.get("ok") and isinstance(payload, dict):
                parts.append(
                    f"**OK** — `{payload.get('name')}` est maintenant "
                    f"**{payload.get('status')}**."
                )
            else:
                parts.append(f"**Échec** `{name}` : {data.get('error') or 'erreur'}")
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
    return body + "\n\nAutre chose ? (stop / start / logs / liste)"


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
                f"- **id {a.get('id')}** `{a.get('name')}` — **{a.get('status')}** — "
                f"port {a.get('port')} — domaine {domain}{extra}"
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
                f"- **id {a.get('id')}** `{a.get('name')}` — **{a.get('status')}** — "
                f"port {a.get('port')}{extra}"
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
    low = text.lower().strip()

    # —— Small talk / politesse (réponses humaines, pas de dump panel) ——
    if re.search(
        r"\b(comment\s+vas[-\s]?tu|ça\s+va|ca\s+va|comment\s+ça\s+va|comment\s+ca\s+va|"
        r"how\s+are\s+you|tu\s+vas\s+bien|quoi\s+de\s+neuf)\b",
        low,
    ):
        return (
            "Ça va très bien, merci 😊 Et toi ?\n\n"
            "Quand tu veux, on peut enchaîner sur ton panel "
            "(apps, domaines, mails, fichiers…) — ou juste discuter."
        )

    if re.search(r"\b(bonjour|salut|hello|hey|coucou|bonsoir)\b", low) and len(low) < 48:
        return (
            "Salut ! Content de te parler.\n\n"
            "Je peux discuter normalement **ou** agir sur ton compte V-zone "
            "(lister/arrêter des apps, domaines, SSL, DB, emails…). "
            "Dis-moi juste ce dont tu as besoin."
        )

    if any(k in low for k in ("merci", "thanks", "nickel", "parfait", "super", "top", "cool")):
        return "Avec plaisir 🙂 Tu as autre chose en tête ?"

    if any(k in low for k in ("au revoir", "bye", "à plus", "a plus", "ciao", "bonne soirée", "bonne nuit")):
        return "À bientôt ! N'hésite pas si tu as besoin du panel."

    if any(
        k in low
        for k in (
            "qui es-tu",
            "tu peux quoi",
            "que peux-tu",
            "tes capacités",
            "tu sais faire",
            "aide-moi",
            "aide moi",
        )
    ):
        return (
            "Je suis **V-zone AI**, l'assistant du panneau.\n\n"
            "En mode local (sans LLM distant) je suis surtout fort pour **agir** :\n"
            "- apps Python/Node (liste, stop, start, logs)\n"
            "- domaines, SSL, bases, emails, fichiers, cron, WP, backups…\n\n"
            "Tu peux aussi me poser une question technique. "
            "Exemple : *liste mes domaines* ou *explique-moi WSGI*."
        )

    if any(k in low for k in ("wsgi", "asgi", "passenger", "gunicorn", "uvicorn")):
        return (
            "- **WSGI** : Django classique (souvent `passenger_wsgi.py` / gunicorn).\n"
            "- **ASGI** : async (FastAPI, uvicorn).\n"
            "- Sur V-zone : app → port local → domaine en reverse-proxy.\n\n"
            "Tu configures Django ou FastAPI ?"
        )

    if any(k in low for k in ("c'est quoi", "cest quoi", "explique", "comment marche", "différenc", "pourquoi")):
        return (
            f"Bonne question sur : « {text[:160]} ».\n\n"
            "En mode local je n'ai pas un grand modèle derrière moi — "
            "pour les longues explications, Ollama change la donne. "
            "Pour **ton** compte, je peux aller chercher les infos live.\n\n"
            "Tu veux une explication courte, ou que je regarde quelque chose sur le panel ?"
        )

    url = ""
    m = re.search(r"(https?://[^\s]+|git@[^\s]+)", text)
    if m:
        url = m.group(1)

    if url or any(k in low for k in ("django", "flask", "fastapi", "déploy", "deploy", "github")):
        return (
            "OK pour le déploiement"
            + (f" (`{url}`)" if url else "")
            + ". Dis-moi où tu en es : repo prêt ? domaine ? erreur sous les yeux ? "
            "On avance message par message."
        )

    # Multi-tours : ne pas forcer le panel sur du bavardage
    if len(user_turns) >= 2 and prev_assistant:
        if len(text) < 80 and not any(
            k in low for k in ("app", "domaine", "log", "mail", "fichier", "ssl", "base", "cron")
        ):
            return (
                f"Oui — « {text[:200]} ».\n\n"
                "Je t'écoute. Tu peux parler librement ; dès que tu veux du concret sur le serveur, "
                "dis par ex. *liste mes apps* ou *montre mes domaines*."
            )
        return (
            f"Compris : « {text[:240]} ».\n\n"
            "Si c'est lié au panel, je peux agir tout de suite "
            "(liste / stop / logs / domaines…). Sinon reformule et j'y réponds au mieux."
        )

    return (
        f"Compris : « {text[:280]} ».\n\n"
        "Dis-moi ce que tu veux — discussion, debug, ou une action panel "
        "(*liste mes applications*, *mes domaines*, *mes mails*…)."
    )
