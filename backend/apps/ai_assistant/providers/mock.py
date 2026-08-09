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

        # Après tool(s) → éventuellement enchaîner stop/start/restart / WP, sinon synthèse
        if messages and messages[-1].role == "tool":
            follow = _lifecycle_after_tools(messages, tool_names, last_user_l)
            if follow is not None:
                return follow
            follow = _wordpress_after_tools(
                messages, tool_names, last_user_l, user_turns=user_turns
            )
            if follow is not None:
                return follow
            follow = _mail_after_tools(
                messages, tool_names, last_user_l, user_turns=user_turns
            )
            if follow is not None:
                return follow
            return ChatResult(
                content=_synthesize_tools(messages),
                provider=self.name,
                model="mock-coach",
            )

        # Intentions d'action — AVANT le bavardage multi-tours
        intent = _detect_intent(last_user_l, messages, tool_names, user_turns=user_turns)
        if intent:
            calls = _pack_calls(tool_names, intent["tools"])
            if calls:
                return ChatResult(
                    content=intent["say"],
                    tool_calls=calls,
                    provider=self.name,
                    model="mock-coach",
                )
            if intent.get("say") and not intent.get("tools"):
                return ChatResult(
                    content=intent["say"],
                    provider=self.name,
                    model="mock-coach",
                )

        return ChatResult(
            content=_converse(last_user, prev_assistant, user_turns, messages=messages),
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


def _extract_hostname(text: str) -> str | None:
    """Extrait un FQDN (ex. wp.7une.info) depuis le message utilisateur."""
    raw = (text or "").lower()
    m = re.search(
        r"(?:sous[-\s]?domaine|domaine|hostname|host|url|sur|pour|avec|"
        r"c['\u2019]?est|cest)\s+"
        r"(?:le\s+|la\s+|l['\u2019]\s*)?(?:https?://)?([a-z0-9][a-z0-9.-]*\.[a-z]{2,})",
        raw,
    )
    if m:
        return m.group(1).rstrip(".").strip()
    found = re.findall(
        r"\b(?:https?://)?([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+)\b",
        raw,
    )
    skip_suffix = (".json", ".py", ".js", ".ts", ".md", ".txt", ".log", ".php")
    for h in found:
        host = h.rstrip(".")
        if any(host.endswith(s) for s in skip_suffix):
            continue
        if host.count(".") < 1:
            continue
        if host in {"wordpress.com", "wordpress.org", "example.com", "localhost.local"}:
            continue
        return host
    return None


def _wants_wordpress_install(text: str) -> bool:
    t = (text or "").lower()
    # Accepte typos fréquents : wordpresse, wp, site/app wordpress
    has_wp = (
        "wordpress" in t
        or "wordpresse" in t
        or "word press" in t
        or bool(re.search(r"\bwp\b", t))
    )
    if not has_wp:
        return False
    return any(
        k in t
        for k in (
            "crée",
            "cree",
            "créer",
            "creer",
            "install",
            "installe",
            "nouveau site",
            "nouvelle install",
            "ajouter un site",
            "setup wordpress",
            "deploy wordpress",
            "une app",
            "une application",
            "un site",
        )
    )


def _wants_go_ahead(text: str) -> bool:
    t = (text or "").lower().strip()
    return bool(
        re.search(
            r"\b("
            r"vas[-\s]?y|allez[-\s]?y|agis|agissez|fais[-\s]?le|fais[-\s]?ça|fais[-\s]?ca|"
            r"go\b|lance|lance[-\s]?toi|ok\s+lance|oui\s+vas|oui\s+go|go\s+ahead|"
            r"exécute|execute|continue|c'?est\s+bon|go\s+go"
            r")\b",
            t,
        )
    )


def _assistant_asked_wp_domain(messages: list[ChatMessage]) -> bool:
    seen = 0
    for m in reversed(messages):
        if m.role != "assistant" or not m.content:
            continue
        if m.content.startswith("(outil"):
            continue
        low = m.content.lower()
        if any(
            k in low
            for k in (
                "domaine ou sous-domaine",
                "indique le **domaine",
                "indique le domaine",
                "sous-domaine cible",
                "prépare l'installation wordpress",
                "installation wordpress",
            )
        ):
            return True
        seen += 1
        if seen >= 4:
            break
    return False


def _pending_wordpress_flow(
    messages: list[ChatMessage],
    user_turns: list[str],
) -> bool:
    """True si on est au milieu d'une création WP (domaine demandé / intent récent)."""
    if _assistant_asked_wp_domain(messages):
        return True
    for turn in reversed(user_turns[:-1] if len(user_turns) > 1 else []):
        if _wants_wordpress_install(turn.lower()):
            return True
        # Stop si autre sujet clair entre-temps
        if len(turn) > 12 and not _extract_hostname(turn.lower()):
            break
    for m in messages:
        if m.role == "system" and '"pending_wp"' in (m.content or ""):
            if re.search(r'"pending_wp"\s*:\s*true', m.content or "", re.I):
                return True
    return False


def _resolve_wp_host(
    last_user_l: str,
    messages: list[ChatMessage],
    user_turns: list[str],
) -> str | None:
    host = _extract_hostname(last_user_l)
    if host:
        return host
    for m in messages:
        if m.role != "system":
            continue
        found = re.search(r'"pending_wp_host"\s*:\s*"([^"]+)"', m.content or "")
        if found:
            return found.group(1).strip().lower()
    for turn in reversed(user_turns[:-1] if len(user_turns) > 1 else []):
        h = _extract_hostname(turn.lower())
        if h:
            return h
    return None


def _wordpress_flow_active(
    last_user_l: str,
    messages: list[ChatMessage],
    user_turns: list[str],
) -> bool:
    if _wants_wordpress_install(last_user_l):
        return True
    pending = _pending_wordpress_flow(messages, user_turns)
    if not pending:
        return False
    if _extract_hostname(last_user_l):
        return True
    if _wants_go_ahead(last_user_l):
        return True
    # Message court du type « le sous domaine c'est … » déjà couvert par hostname
    return False


def _create_verb(text: str) -> bool:
    t = (text or "").lower()
    return any(
        k in t
        for k in (
            "crée",
            "cree",
            "créer",
            "creer",
            "ajouter",
            "nouveau fichier",
            "nouvelle fichier",
            "touch ",
            "écris",
            "ecris",
            "écrire",
            "ecrire",
            "write ",
            "create ",
        )
    )


def _wants_write_file(text: str) -> bool:
    t = (text or "").lower()
    if not _create_verb(t):
        return False
    if any(k in t for k in ("dossier", "répertoire", "repertoire", "folder", "mkdir")):
        return False
    if any(k in t for k in ("fichier", "file")):
        return True
    # « crée lievin.txt » / « crée notes.md »
    return bool(re.search(r"\b[\w./-]+\.[a-z0-9]{1,12}\b", t))


def _wants_mkdir(text: str) -> bool:
    t = (text or "").lower()
    if not _create_verb(t) and "mkdir" not in t:
        return False
    return any(k in t for k in ("dossier", "répertoire", "repertoire", "folder", "mkdir", "directory"))


def _wants_delete_path(text: str) -> bool:
    t = (text or "").lower()
    if not any(k in t for k in ("supprime", "supprimer", "efface", "effacer", "delete", "rm ")):
        return False
    return any(k in t for k in ("fichier", "file", "dossier", "répertoire", "repertoire", "folder")) or bool(
        re.search(r"\b[\w./-]+\.[a-z0-9]{1,12}\b", t)
    )


def _extract_path_name(text: str, *, kind: str = "any") -> str | None:
    """Nom/chemin relatif (ex. lievin.txt, logs, apps/notes.md)."""
    raw = (text or "").strip()
    # du nom X / nommé X / appelé X
    m = re.search(
        r"(?:du\s+nom|nomm[ée]e?|nomme|appel[ée]e?|called|named)\s+"
        r"[«\"'`]?([^\s«»\"'`]+)",
        raw,
        re.I,
    )
    if m:
        return m.group(1).strip("/\\")
    # fichier|dossier X
    m = re.search(
        r"(?:fichier|file|dossier|r[ée]pertoire|folder|dir|directory)\s+"
        r"(?:du\s+nom\s+|nomm[ée]e?\s+|appel[ée]e?\s+)?"
        r"[«\"'`]?([a-zA-Z0-9._/-]+)",
        raw,
        re.I,
    )
    if m:
        name = m.group(1).strip("/\\")
        if name.lower() in {"du", "un", "une", "le", "la", "de", "des", "nom", "nouveau", "nouvelle"}:
            pass
        else:
            return name
    # extension classique
    m = re.search(r"\b([a-zA-Z0-9._/-]+\.[a-zA-Z0-9]{1,12})\b", raw)
    if m and kind in {"file", "any"}:
        hostish = m.group(1).lower()
        if hostish.count(".") >= 2 and not any(
            hostish.endswith(ext)
            for ext in (
                ".txt",
                ".md",
                ".py",
                ".js",
                ".ts",
                ".json",
                ".html",
                ".css",
                ".log",
                ".env",
                ".yml",
                ".yaml",
                ".ini",
                ".conf",
                ".cfg",
                ".sh",
                ".php",
                ".sql",
                ".xml",
                ".csv",
            )
        ):
            # évite de prendre un domaine pour un fichier
            pass
        else:
            return m.group(1).strip("/\\")
    if kind in {"dir", "any"}:
        m = re.search(
            r"(?:mkdir|dossier|folder|r[ée]pertoire)\s+[«\"'`]?([a-zA-Z0-9._/-]+)",
            raw,
            re.I,
        )
        if m:
            return m.group(1).strip("/\\")
    return None


def _extract_file_content(text: str) -> str:
    raw = text or ""
    m = re.search(
        r"(?:contenu|content|texte|avec)\s*[:=]?\s*[«\"'](.+?)[»\"']\s*$",
        raw,
        re.I | re.S,
    )
    if m:
        return m.group(1)[:8000]
    m = re.search(r"(?:contenu|content)\s*[:=]\s*(.+)$", raw, re.I | re.S)
    if m:
        return m.group(1).strip()[:8000]
    return ""


def _page_meta(messages: list[ChatMessage]) -> dict[str, str]:
    """Label / runtime / path UI — sans le JSON session (évite faux positifs `python_apps`)."""
    label, runtime, path, need = "", "", "", ""
    for m in messages:
        if m.role != "system" or "page actuelle" not in (m.content or "").lower():
            continue
        content = m.content or ""
        cut = content.split("\n{", 1)[0]
        low = cut.lower()
        ml = re.search(r"page actuelle:\s*([^\n(]+)", low)
        if ml:
            label = ml.group(1).strip()
        mp = re.search(r"page actuelle:[^\n]*\(([^)]+)\)", low)
        if mp:
            path = mp.group(1).strip()
        mr = re.search(r"runtime page:\s*(\S+)", low)
        if mr and mr.group(1) not in {"n/a", "na", "-"}:
            runtime = mr.group(1).strip()
        mn = re.search(r"besoin immédiat:\s*([^\n]+)", low)
        if mn:
            need = mn.group(1).strip()
    return {"label": label, "runtime": runtime, "path": path, "need": need}


def _page_section(meta: dict[str, str]) -> str:
    label = (meta.get("label") or "").lower()
    path = (meta.get("path") or "").lower()
    blob = f"{label} {path}"
    mapping = (
        ("wordpress", "wordpress"),
        ("file manager", "files"),
        ("fichier", "files"),
        ("/files", "files"),
        ("email", "email"),
        ("mail", "email"),
        ("ftp", "ftp"),
        ("cron", "cron"),
        ("backup", "backups"),
        ("docker", "docker"),
        ("kubernetes", "k8s"),
        ("domaine", "domains"),
        ("dns", "dns"),
        ("database", "databases"),
        ("bases", "databases"),
        ("python", "python"),
        ("node", "node"),
        ("git", "git"),
        ("php", "php"),
        ("sécurité", "security"),
        ("securite", "security"),
        ("package", "package"),
        ("terminal", "terminal"),
    )
    for needle, sec in mapping:
        if needle in blob:
            return sec
    return ""


def _wants_create_mailbox(text: str) -> bool:
    t = (text or "").lower()
    if not _create_verb(t):
        return False
    return any(
        k in t
        for k in (
            "messagerie",
            "mailbox",
            "boîte mail",
            "boite mail",
            "compte mail",
            "compte email",
            "compte de messagerie",
            "adresse mail",
            "adresse email",
            "courriel",
            "e-mail",
            "email",
        )
    ) or (
        "mail" in t
        and any(k in t for k in ("compte", "boîte", "boite", "adresse", "nouveau", "nouveua"))
    )


def _extract_email_address(text: str) -> tuple[str, str] | None:
    m = re.search(
        r"\b([a-z0-9](?:[a-z0-9._+-]{0,62}[a-z0-9])?)@([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,})\b",
        (text or "").lower(),
    )
    if not m:
        return None
    return m.group(1), m.group(2)


def _extract_mailbox_password(text: str) -> str:
    raw = text or ""
    m = re.search(
        r"(?:mot\s*de\s*passe|password|mdp|pass)\s*[:=]?\s*[«\"']?([^\s«»\"']{8,128})",
        raw,
        re.I,
    )
    return (m.group(1) if m else "").strip()


def _mailboxes_from_tool_payload(data: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict):
        return [], []
    domains = [d for d in (payload.get("domains") or []) if isinstance(d, dict)]
    boxes = [b for b in (payload.get("mailboxes") or []) if isinstance(b, dict)]
    return domains, boxes


def _mail_after_tools(
    messages: list[ChatMessage],
    tool_names: set[str],
    last_user_l: str,
    *,
    user_turns: list[str] | None = None,
) -> ChatResult | None:
    turns = user_turns or []
    if not _wants_create_mailbox(last_user_l):
        # Intent sur un tour précédent + détails maintenant
        pending = any(_wants_create_mailbox(t.lower()) for t in turns[:-1]) if len(turns) > 1 else False
        if not pending and not _extract_email_address(last_user_l):
            return None

    recent: list[ChatMessage] = []
    for m in reversed(messages):
        if m.role != "tool":
            break
        recent.append(m)
    recent.reverse()
    if not recent:
        return None
    if not any((m.name or "") == "list_mailboxes" for m in recent):
        return None
    if any((m.name or "") == "create_mailbox" for m in recent):
        return None

    domains: list[dict] = []
    boxes: list[dict] = []
    for m in recent:
        if (m.name or "") != "list_mailboxes":
            continue
        try:
            data = json.loads(m.content or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            domains, boxes = _mailboxes_from_tool_payload(data)

    addr = _extract_email_address(last_user_l)
    if not addr:
        for t in reversed(turns):
            addr = _extract_email_address(t.lower())
            if addr:
                break
    if not addr:
        sample = ", ".join(f"`{d.get('name')}`" for d in domains[:6]) if domains else "(aucun domaine mail)"
        return ChatResult(
            content=(
                "Pour créer une boîte, indique **adresse + mot de passe** (≥8).\n"
                f"Domaines mail dispo : {sample}\n"
                "Exemple : *crée contact@exemple.com mot de passe MonMotDePasse9*"
            ),
            provider="mock",
            model="mock-coach",
        )

    local_part, domain_name = addr
    match = next(
        (d for d in domains if str(d.get("name") or "").lower() == domain_name),
        None,
    )
    if not match:
        return ChatResult(
            content=(
                f"Le domaine mail **{domain_name}** n'est pas sur ce compte. "
                "Crée d’abord le domaine mail (page Email), ou choisis un domaine listé."
            ),
            provider="mock",
            model="mock-coach",
        )

    already = next(
        (
            b
            for b in boxes
            if str(b.get("local_part") or "").lower() == local_part
            and str(b.get("domain") or "").lower() == domain_name
        ),
        None,
    )
    if already:
        return ChatResult(
            content=f"La boîte **{local_part}@{domain_name}** existe déjà (id {already.get('id')}).",
            provider="mock",
            model="mock-coach",
        )

    password = ""
    for t in reversed(turns or [last_user_l]):
        password = _extract_mailbox_password(t)
        if password:
            break
    if not password or len(password) < 8:
        return ChatResult(
            content=(
                f"Domaine OK pour **{local_part}@{domain_name}**. "
                "Il me faut un **mot de passe ≥ 8 caractères** "
                "(ex. *mot de passe MonSecret123*). "
                "Je ne l’afficherai pas après confirmation."
            ),
            provider="mock",
            model="mock-coach",
        )

    if "create_mailbox" not in tool_names:
        return None
    return ChatResult(
        content=(
            f"Je prépare la création de **{local_part}@{domain_name}** — "
            "clique **Exécuter** pour confirmer (mot de passe masqué)."
        ),
        tool_calls=[
            ToolCallRequest(
                id=str(uuid4()),
                name="create_mailbox",
                arguments={
                    "mail_domain_id": int(match["id"]),
                    "local_part": local_part,
                    "password": password,
                    "quota_mb": 1024,
                },
            )
        ],
        provider="mock",
        model="mock-coach",
    )


def _parent_hostname(host: str) -> str | None:
    parts = (host or "").strip(".").split(".")
    if len(parts) < 3:
        return None
    return ".".join(parts[1:])


def _domains_from_tool_payload(data: dict[str, Any]) -> list[dict]:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict):
        return []
    items = payload.get("domains") or []
    return [d for d in items if isinstance(d, dict)]


def _wp_sites_from_tool_payload(data: dict[str, Any]) -> list[dict]:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict):
        return []
    items = payload.get("sites") or []
    return [s for s in items if isinstance(s, dict)]


def _wordpress_after_tools(
    messages: list[ChatMessage],
    tool_names: set[str],
    last_user_l: str,
    *,
    user_turns: list[str] | None = None,
) -> ChatResult | None:
    """Après list_domains / list_wordpress : propose create_domain ou install_wordpress."""
    turns = user_turns or []
    if not _wordpress_flow_active(last_user_l, messages, turns):
        return None

    recent: list[ChatMessage] = []
    for m in reversed(messages):
        if m.role != "tool":
            break
        recent.append(m)
    recent.reverse()
    if not recent:
        return None

    names = {(m.name or "") for m in recent}
    if "install_wordpress" in names:
        return None

    # create_domain vient de réussir → enchaîner l'install WP
    for m in recent:
        if (m.name or "") != "create_domain":
            continue
        try:
            data = json.loads(m.content or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("pending_confirmation"):
            return None
        if not data.get("ok", True):
            return None
        payload = data.get("data") if isinstance(data.get("data"), dict) else None
        if payload is None and isinstance(data.get("result"), dict):
            payload = data["result"]
        if payload is None:
            payload = data
        if not isinstance(payload, dict):
            continue
        did = payload.get("id")
        if did and "install_wordpress" in tool_names:
            title = str(payload.get("name") or "Mon site").split(".")[0] or "Mon site"
            return ChatResult(
                content=(
                    f"Domaine **{payload.get('name')}** prêt. "
                    "Je prépare l'installation WordPress — clique **Exécuter** pour confirmer."
                ),
                tool_calls=[
                    ToolCallRequest(
                        id=str(uuid4()),
                        name="install_wordpress",
                        arguments={
                            "domain_id": int(did),
                            "title": title[:80],
                            "admin_user": "admin",
                        },
                    )
                ],
                provider="mock",
                model="mock-coach",
            )

    if "list_domains" not in names:
        return None

    domains: list[dict] = []
    wp_sites: list[dict] = []
    for m in recent:
        try:
            data = json.loads(m.content or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if (m.name or "") == "list_domains":
            domains = _domains_from_tool_payload(data)
        elif (m.name or "") == "list_wordpress_sites":
            wp_sites = _wp_sites_from_tool_payload(data)

    host = _resolve_wp_host(last_user_l, messages, turns)
    if not host:
        return ChatResult(
            content=(
                "Pour installer WordPress, indique le **domaine ou sous-domaine** cible.\n"
                "Exemple : *crée un site WordPress sur blog.exemple.com*"
            ),
            provider="mock",
            model="mock-coach",
        )

    match = next(
        (d for d in domains if str(d.get("name") or "").lower() == host),
        None,
    )
    if match:
        did = int(match.get("id") or 0)
        already = next(
            (s for s in wp_sites if int(s.get("domain_id") or 0) == did),
            None,
        )
        if already:
            return ChatResult(
                content=(
                    f"WordPress est **déjà installé** sur `{host}` "
                    f"(site #{already.get('id')} — {already.get('site_url') or already.get('title')}).\n\n"
                    "Autre chose ? (SSL / liste / supprimer)"
                ),
                provider="mock",
                model="mock-coach",
            )
        if "install_wordpress" not in tool_names or not did:
            return None
        title = host.split(".")[0] or "Mon site"
        return ChatResult(
            content=(
                f"Le domaine **{host}** existe (id {did}). "
                "Je prépare **install_wordpress** — clique **Exécuter** pour confirmer."
            ),
            tool_calls=[
                ToolCallRequest(
                    id=str(uuid4()),
                    name="install_wordpress",
                    arguments={
                        "domain_id": did,
                        "title": title[:80],
                        "admin_user": "admin",
                    },
                )
            ],
            provider="mock",
            model="mock-coach",
        )

    # Domaine absent → créer le sous-domaine si parent connu
    parent_name = _parent_hostname(host)
    parent = None
    if parent_name:
        parent = next(
            (d for d in domains if str(d.get("name") or "").lower() == parent_name),
            None,
        )
    if parent and "create_domain" in tool_names:
        return ChatResult(
            content=(
                f"**{host}** n'existe pas encore. Je prépare la création du sous-domaine "
                f"sous **{parent.get('name')}** — clique **Exécuter**, "
                "puis j'enchaînerai l'installation WordPress."
            ),
            tool_calls=[
                ToolCallRequest(
                    id=str(uuid4()),
                    name="create_domain",
                    arguments={
                        "name": host,
                        "domain_type": "subdomain",
                        "parent_id": int(parent["id"]),
                        "create_dns_zone": True,
                    },
                )
            ],
            provider="mock",
            model="mock-coach",
        )

    lines = [
        f"Je ne trouve pas **{host}** dans tes domaines.",
    ]
    if parent_name and not parent:
        lines.append(
            f"Le parent **{parent_name}** est aussi absent — crée d'abord ce domaine "
            "(page Domaines), puis redemande l'install WP."
        )
    elif domains:
        sample = ", ".join(f"`{d.get('name')}`" for d in domains[:8])
        lines.append(f"Domaines disponibles : {sample}")
        lines.append("Indique un domaine existant, ou crée le sous-domaine dans Domaines.")
    return ChatResult(
        content="\n".join(lines),
        provider="mock",
        model="mock-coach",
    )


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
    *,
    user_turns: list[str] | None = None,
) -> dict | None:
    turns = user_turns or []
    page = _page_meta(messages)
    page_sec = _page_section(page)
    page_runtime = (page.get("runtime") or "").lower()
    page_blob = f"{page.get('label', '')} {page.get('path', '')} {page.get('need', '')} {page_runtime}".lower()

    lifecycle = _lifecycle_verb(last_user_l)
    if lifecycle:
        runtime = _guess_runtime(last_user_l + " " + page_runtime)
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

    # WordPress : créer / installer (+ suite « le sous-domaine c'est X » / « vas-y »)
    if _wordpress_flow_active(last_user_l, messages, turns):
        host = _resolve_wp_host(last_user_l, messages, turns)
        say = "Je prépare l'installation WordPress"
        if host:
            say += f" sur **{host}**"
        say += " — je vérifie d'abord tes domaines et sites WP…"
        return {
            "say": say,
            "tools": [("list_domains", {}), ("list_wordpress_sites", {})],
        }
    if any(k in last_user_l for k in ("wordpress", "wordpresse", "wp ")) or (wants_list and "wp" in last_user_l):
        return {"say": "Je liste tes sites WordPress…", "tools": [("list_wordpress_sites", {})]}
    if "wordpress" in page_blob and any(
        k in last_user_l for k in ("aide", "help", "je suis sur", "sites wp")
    ):
        return {
            "say": (
                "Tu es sur WordPress. Je liste tes sites. "
                "Pour en créer un : *crée un site WordPress sur sous.domaine.tld*."
            ),
            "tools": [("list_wordpress_sites", {})],
        }

    # Aide contextuelle page (avant les faux positifs apps / « compte »)
    page_help = any(
        k in last_user_l
        for k in ("aide", "help", "je suis sur", "aide-moi", "aide moi", "que faire")
    )
    if page_help or any(
        k in last_user_l for k in ("comptes mail", "boîtes mail", "boites mail", "messagerie")
    ):
        if page_sec == "email" or any(
            k in last_user_l for k in ("email", "mail", "messagerie", "boîte", "boite")
        ):
            if _wants_create_mailbox(last_user_l):
                pass  # handled below
            elif page_sec == "email" or page_help:
                return {
                    "say": (
                        "Tu es sur Email. Je liste tes domaines mail et boîtes. "
                        "Pour créer : *crée contact@domaine.tld mot de passe Secret1234*."
                    ),
                    "tools": [("list_mailboxes", {})],
                }
        if page_sec == "ftp":
            return {"say": "Tu es sur FTP. Je liste tes comptes…", "tools": [("list_ftp_accounts", {})]}
        if page_sec == "cron":
            return {"say": "Tu es sur Cron. Je liste tes tâches…", "tools": [("list_cron_jobs", {})]}
        if page_sec == "backups":
            return {"say": "Tu es sur Backups. Je liste tes sauvegardes…", "tools": [("list_backups", {})]}
        if page_sec == "files":
            return {"say": "Tu es sur File Manager. Je liste le home…", "tools": [("list_files", {"path": ""})]}
        if page_sec == "domains":
            return {"say": "Tu es sur Domaines. Je liste tes domaines…", "tools": [("list_domains", {})]}
        if page_sec == "databases":
            return {"say": "Tu es sur Databases. Je liste tes bases…", "tools": [("list_databases", {})]}
        if page_sec == "dns":
            return {"say": "Tu es sur DNS. Je liste tes zones…", "tools": [("list_dns_zones", {})]}

    if _wants_create_mailbox(last_user_l):
        addr = _extract_email_address(last_user_l)
        say = "Je prépare la création d'une boîte mail"
        if addr:
            say += f" **{addr[0]}@{addr[1]}**"
        say += " — je vérifie d'abord tes domaines mail…"
        return {"say": say, "tools": [("list_mailboxes", {})]}

    # Fichiers : créer / écrire AVANT le simple listage
    if _wants_mkdir(last_user_l):
        name = _extract_path_name(last_user_l, kind="dir")
        if name and "mkdir_path" in tool_names:
            return {
                "say": (
                    f"Je prépare la création du dossier **{name}** — "
                    "clique **Exécuter** pour confirmer."
                ),
                "tools": [("mkdir_path", {"path": name})],
            }
        return {
            "say": (
                "Pour créer un dossier, indique le nom.\n"
                "Exemple : *crée un dossier logs*"
            ),
        }
    if _wants_write_file(last_user_l):
        path = _extract_path_name(last_user_l, kind="file")
        if path and "write_file" in tool_names:
            content = _extract_file_content(last_user_l)
            return {
                "say": (
                    f"Je prépare la création du fichier **{path}** — "
                    "clique **Exécuter** pour confirmer."
                ),
                "tools": [("write_file", {"path": path, "content": content})],
            }
        return {
            "say": (
                "Pour créer un fichier, indique le nom (ex. `notes.txt`).\n"
                "Exemple : *crée un fichier du nom lievin.txt*"
            ),
        }
    if _wants_delete_path(last_user_l):
        path = _extract_path_name(last_user_l, kind="any")
        if path and "delete_paths" in tool_names:
            return {
                "say": (
                    f"Je prépare la suppression de **{path}** — "
                    "clique **Exécuter** pour confirmer."
                ),
                "tools": [("delete_paths", {"paths": [path]})],
            }

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

    if wants_list and any(k in last_user_l for k in ("mail", "email", "boîte", "boite", "mailbox", "messagerie")):
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

    if wants_list and (mentions_python or mentions_node or mentions_apps):
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
    on_python_page = page_sec == "python" or page_runtime == "python"
    on_node_page = page_sec == "node" or page_runtime == "node"
    if (on_python_page or mentions_python) and (
        "log" in last_user_l or "statut" in last_user_l or (page_auto and on_python_page)
    ):
        return {
            "say": "Ok, je regarde le statut et les logs Python…",
            "tools": [
                ("check_application_status", {}),
                ("get_page_logs", {"runtime": "python", "lines": 100}),
                ("analyze_deployment_error", {"runtime": "python"}),
            ],
        }

    if (on_node_page or mentions_node) and (
        "log" in last_user_l or "statut" in last_user_l or (page_auto and on_node_page)
    ):
        return {
            "say": "Ok, je regarde tes apps Node et les logs…",
            "tools": [
                ("check_application_status", {}),
                ("get_page_logs", {"runtime": "node", "lines": 100}),
            ],
        }

    if any(k in last_user_l for k in ("log", "erreur", "error", "failed", "échou", "traceback")):
        rt = _guess_runtime(last_user_l + " " + page_runtime)
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

    if any(
        k in last_user_l
        for k in (
            "contexte",
            "ce que j'ai",
            "ce que j ai",
            "mon compte",
            "vue d'ensemble",
            "sur mon compte",
        )
    ) and "messagerie" not in last_user_l and "mail" not in last_user_l:
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
        elif name == "list_files":
            parts.append(_format_files(data))
        elif name == "list_mailboxes":
            parts.append(_format_mailboxes(data))
        elif name == "list_domains":
            parts.append(_format_domains_list(data))
        elif name == "list_databases":
            parts.append(_format_databases(data))
        elif name == "list_wordpress_sites":
            parts.append(_format_wordpress_sites(data))
        elif name == "list_ftp_accounts":
            parts.append(_format_simple_list(data, "FTP", "accounts", "username"))
        elif name == "list_backups":
            parts.append(_format_simple_list(data, "Sauvegardes", "backups", "name"))
        elif name == "list_cron_jobs":
            parts.append(_format_simple_list(data, "Cron", "jobs", "command"))
        elif name == "get_account_overview":
            parts.append(_format_overview(data))
        else:
            ok = data.get("ok", True)
            err = data.get("error")
            if err:
                parts.append(f"**{name}** : erreur — {err}")
            else:
                snippet = json.dumps(data.get("data", data), ensure_ascii=False)[:600]
                parts.append(f"**{name}** — OK.\n```json\n{snippet}\n```")

    body = "\n\n".join(p for p in parts if p) or "Aucune donnée retournée par les outils."
    names_used = {(m.name or "") for m in tool_msgs}
    if names_used & {"list_wordpress_sites", "install_wordpress", "delete_wordpress", "create_domain"}:
        footer = "\n\nAutre chose ? (installer WP / SSL / liste domaines)"
    elif names_used & {"list_domains", "issue_ssl_certificate", "get_ssl_status"}:
        footer = "\n\nAutre chose ? (SSL / WordPress / liste)"
    elif names_used & {"list_mailboxes", "create_mailbox"}:
        footer = "\n\nAutre chose ? (créer une boîte / DKIM / liste)"
    elif names_used & {"list_files", "write_file", "mkdir_path"}:
        footer = "\n\nAutre chose ? (créer fichier / dossier / chercher)"
    else:
        footer = "\n\nDis-moi la suite quand tu veux."
    return body + footer


def _payload(data: dict) -> dict:
    if isinstance(data.get("data"), dict):
        return data["data"]
    if isinstance(data.get("result"), dict):
        return data["result"]
    return data


def _format_files(data: dict) -> str:
    payload = _payload(data)
    entries = payload.get("entries") or []
    cwd = payload.get("cwd") or "/"
    lines = [f"**Fichiers** — `{cwd or 'home'}` ({len(entries)} éléments)", ""]
    dirs = [e for e in entries if isinstance(e, dict) and e.get("is_dir")]
    files = [e for e in entries if isinstance(e, dict) and not e.get("is_dir")]
    if dirs:
        lines.append("**Dossiers**")
        for e in dirs[:24]:
            lines.append(f"- 📁 `{e.get('name')}`")
        if len(dirs) > 24:
            lines.append(f"- … +{len(dirs) - 24} dossiers")
        lines.append("")
    if files:
        lines.append("**Fichiers**")
        for e in files[:24]:
            size = e.get("size")
            sz = f" · {size} o" if isinstance(size, int) and size else ""
            lines.append(f"- 📄 `{e.get('name')}`{sz}")
        if len(files) > 24:
            lines.append(f"- … +{len(files) - 24} fichiers")
    if not dirs and not files:
        lines.append("_Dossier vide._")
    return "\n".join(lines)


def _format_mailboxes(data: dict) -> str:
    payload = _payload(data)
    domains = [d for d in (payload.get("domains") or []) if isinstance(d, dict)]
    boxes = [b for b in (payload.get("mailboxes") or []) if isinstance(b, dict)]
    lines = ["**Messagerie**", ""]
    lines.append(f"**Domaines mail** ({len(domains)})")
    if not domains:
        lines.append("- Aucun domaine mail.")
    else:
        for d in domains[:12]:
            lines.append(f"- `{d.get('name')}`")
    lines.append("")
    lines.append(f"**Boîtes** ({len(boxes)})")
    if not boxes:
        lines.append("- Aucune boîte pour l’instant.")
    else:
        for b in boxes[:20]:
            addr = b.get("address") or f"{b.get('local_part')}@{b.get('domain')}"
            st = "active" if b.get("is_active") and not b.get("is_suspended") else "inactive"
            lines.append(f"- **{addr}** — {st}")
    return "\n".join(lines)


def _format_domains_list(data: dict) -> str:
    payload = _payload(data)
    domains = [d for d in (payload.get("domains") or []) if isinstance(d, dict)]
    lines = [f"**Domaines** ({len(domains)})", ""]
    if not domains:
        lines.append("- Aucun domaine.")
    else:
        for d in domains[:25]:
            lines.append(f"- **id {d.get('id')}** `{d.get('name')}`")
    return "\n".join(lines)


def _format_databases(data: dict) -> str:
    payload = _payload(data)
    items = [d for d in (payload.get("databases") or payload.get("items") or []) if isinstance(d, dict)]
    lines = [f"**Bases de données** ({len(items)})", ""]
    if not items:
        lines.append("- Aucune base.")
    else:
        for d in items[:25]:
            engine = d.get("engine") or d.get("type") or ""
            lines.append(f"- **{d.get('name')}** {f'({engine})' if engine else ''}".rstrip())
    return "\n".join(lines)


def _format_wordpress_sites(data: dict) -> str:
    payload = _payload(data)
    sites = [s for s in (payload.get("sites") or []) if isinstance(s, dict)]
    overview = payload.get("overview") if isinstance(payload.get("overview"), dict) else {}
    lines = [f"**Sites WordPress** ({len(sites)})", ""]
    if overview:
        lines.append(
            f"_Résumé_ : {overview.get('sites', len(sites))} site(s), "
            f"{overview.get('active', '—')} actif(s)."
        )
        lines.append("")
    if not sites:
        lines.append("- Aucun site WP.")
    else:
        for s in sites[:20]:
            lines.append(
                f"- **#{s.get('id')}** {s.get('title') or 'Site'} — "
                f"`{s.get('site_url') or '—'}` — **{s.get('status') or '—'}**"
            )
    return "\n".join(lines)


def _format_simple_list(data: dict, title: str, key: str, label_key: str) -> str:
    payload = _payload(data)
    items = [x for x in (payload.get(key) or []) if isinstance(x, dict)]
    lines = [f"**{title}** ({len(items)})", ""]
    if not items:
        lines.append("- Aucun élément.")
    else:
        for x in items[:20]:
            label = x.get(label_key) or x.get("name") or x.get("id") or "?"
            lines.append(f"- `{label}`")
    return "\n".join(lines)


def _format_overview(data: dict) -> str:
    payload = _payload(data)
    pkg = payload.get("my_package") or "—"
    disk = payload.get("disk") if isinstance(payload.get("disk"), dict) else {}
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    lines = [
        "**Vue d’ensemble**",
        "",
        f"- Compte : **{account.get('username') or '—'}**",
        f"- Package : **{pkg}**",
    ]
    if disk:
        lines.append(
            f"- Disque : **{disk.get('used_mb', '?')} Mo** / "
            f"{disk.get('quota_mb', '?')} Mo ({disk.get('percent', '?')} %)"
        )
    if usage:
        bits = ", ".join(f"{k}={v}" for k, v in list(usage.items())[:8])
        lines.append(f"- Usage : {bits}")
    return "\n".join(lines)


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


def _converse(
    last_user: str,
    prev_assistant: str,
    user_turns: list[str],
    *,
    messages: list[ChatMessage] | None = None,
) -> str:
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

    if re.search(
        r"\b(tu\s+connais\s+mon\s+nom|quel\s+est\s+mon\s+nom|mon\s+pseudo|"
        r"comment\s+je\s+m['\u2019]appelle|who\s+am\s+i)\b",
        low,
    ):
        username = ""
        for m in messages or []:
            if m.role != "system" or not m.content:
                continue
            found = re.search(r'"username"\s*:\s*"([^"]+)"', m.content)
            if found:
                username = found.group(1).strip()
                break
        if username:
            return (
                f"Oui — ton identifiant panel est **{username}**.\n\n"
                "Tu veux que je fasse quelque chose sur ton compte ?"
            )
        return (
            "Je n'ai pas ton nom d'utilisateur dans ce tour — "
            "rafraîchis la conversation ou dis-moi ton identifiant panel."
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
