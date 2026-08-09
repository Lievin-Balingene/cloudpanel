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
            follow = _django_after_tools(
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


def _looks_like_shell_or_jail(text: str) -> bool:
    """True si le message vise une commande shell/jail, pas un start/stop d'app."""
    t = _norm_text(text)
    if any(
        k in t
        for k in (
            "commande",
            "command",
            "jail",
            "run_jail",
            "dans le terminal",
            "dans le shell",
        )
    ):
        return True
    # Jetons shell courants (évite « lance une commande ls » → start_application)
    if re.search(r"(?:^|[\s«\"'`])(ls|pwd|df|whoami|uname|pip|npm)(?:\s|$|-\w)", t):
        return True
    return False


def _resolve_jail_command_id(text: str) -> str | None:
    """Mappe un message utilisateur vers un id catalogue jail (whitelist)."""
    t = _norm_text(text)
    if not t:
        return None
    # Catalogue explicite
    for cid in (
        "ls_home",
        "ls_app",
        "pwd",
        "df_home",
        "python_version",
        "node_version",
        "npm_version",
        "du_app",
        "tail_error_log",
        "tail_access_log",
        "pip_freeze_venv",
    ):
        if cid.replace("_", " ") in t or cid in t:
            return cid

    wants_app_scope = any(
        k in t for k in ("app", "application", "projet", "relative_root", "venv")
    )

    if re.search(r"(?:^|[\s«\"'`])ls(?:\s|$|-\w)", t) or "lister le home" in t:
        return "ls_app" if wants_app_scope else "ls_home"
    if re.search(r"(?:^|[\s«\"'`])pwd(?:\s|$)", t) or "repertoire courant" in t:
        return "pwd"
    if re.search(r"(?:^|[\s«\"'`])df(?:\s|$|-\w)", t) or "espace disque" in t:
        return "df_home"
    if "python" in t and ("version" in t or "--version" in t):
        return "python_version"
    if re.search(r"\bnode\b", t) and ("version" in t or "-v" in t):
        return "node_version"
    if re.search(r"\bnpm\b", t) and ("version" in t or "-v" in t):
        return "npm_version"
    if "pip freeze" in t or ("pip" in t and "freeze" in t):
        return "pip_freeze_venv"
    if "error.log" in t or ("tail" in t and "error" in t):
        return "tail_error_log"
    if "access.log" in t or ("tail" in t and "access" in t):
        return "tail_access_log"
    if "du " in t or "taille du dossier" in t:
        return "du_app" if wants_app_scope else None

    # « lance une commande » / « exécute » sans id clair → proposer ls_home si listage
    if any(k in t for k in ("commande", "command", "execute", "executer", "run ")) and any(
        k in t for k in ("ls", "list", "liste", "home", "dossier")
    ):
        return "ls_home"
    return None


def _jail_needs_app(command_id: str) -> bool:
    return command_id in {
        "ls_app",
        "du_app",
        "tail_error_log",
        "tail_access_log",
        "pip_freeze_venv",
    }


def _lifecycle_verb(text: str) -> str | None:
    """Retourne stop|start|restart selon l'intention utilisateur (mots entiers)."""
    import unicodedata

    raw = (text or "").lower().strip()
    # Normalise accents : démarrer → demarrer (évite les faux positifs substring)
    t = "".join(
        c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn"
    )

    # « lance une commande ls » ≠ démarrer une application
    if _looks_like_shell_or_jail(t):
        explicit_app_lifecycle = bool(
            re.search(
                r"\b(demarr\w*|start\w*|stop\w*|arret\w*|redemarr\w*|reboot\w*)\b",
                t,
            )
        ) and any(k in t for k in ("app", "application", "python", "node", "service"))
        if not explicit_app_lifecycle:
            return None

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


def _wants_django_deploy(text: str) -> bool:
    t = _norm_text(text)
    deployish = any(
        k in t
        for k in (
            "deploy",
            "deployer",
            "deploie",
            "deploiement",
            "mise en prod",
            "depuis zero",
            "from scratch",
            "nouvelle app",
            "nouveau projet",
            "mettre en ligne",
            "publier",
        )
    )
    djangoish = any(
        k in t
        for k in ("django", "flask", "fastapi", "wsgi", "asgi", "gunicorn", "uvicorn")
    )
    python_app = ("python" in t and "app" in t) or "app python" in t
    if djangoish and (deployish or any(k in t for k in ("cree", "creer", "installe", "nouvelle", "nouveau"))):
        return True
    if deployish and (djangoish or python_app or "projet" in t):
        return True
    return False


def _extract_project_folder(text: str) -> str | None:
    raw = (text or "").strip()
    m = re.search(
        r"(?:dossier|folder|repertoire|répertoire|projet|chemin|app(?:lication)?\s+root)\s+"
        r"(?:s['\u2019]?appelle\s+|nomm[ée]e?\s+|du\s+nom\s+|c['\u2019]?est\s+)?"
        r"[«\"'`]?([a-zA-Z0-9._/-]+)",
        raw,
        re.I,
    )
    if m:
        name = m.group(1).strip("/\\")
        if name.lower() not in {"le", "la", "un", "une", "du", "de", "des", "mon", "mes", "projet"}:
            return name
    m = re.search(
        r"\b([a-zA-Z0-9_-]+)\s+contient\s+(?:le\s+)?projet",
        raw,
        re.I,
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        r"(?:dans|sur)\s+(?:le\s+)?(?:dossier\s+)?[«\"'`]?([a-zA-Z0-9._/-]+)[»\"'`]?\s*$",
        raw,
        re.I,
    )
    if m and "." not in m.group(1):  # pas un domaine
        return m.group(1).strip("/\\")
    return None


def _pending_django_deploy(messages: list[ChatMessage], user_turns: list[str]) -> bool:
    for m in messages:
        if m.role == "system" and '"pending_deploy"' in (m.content or ""):
            if re.search(r'"pending_deploy"\s*:\s*true', m.content or "", re.I):
                return True
    for turn in reversed(user_turns[:-1] if len(user_turns) > 1 else []):
        if _wants_django_deploy(turn):
            return True
        if len(turn) > 40 and not _extract_project_folder(turn) and not _extract_hostname(turn.lower()):
            break
    for m in reversed(messages):
        if m.role != "assistant" or not m.content:
            continue
        if m.content.startswith("(outil"):
            continue
        low = m.content.lower()
        if any(
            k in low
            for k in (
                "déploiement django",
                "deploy django",
                "application root",
                "dossier du projet",
                "prépare la création de l'app",
                "création de l'app python",
            )
        ):
            return True
        break
    return False


def _resolve_deploy_root(
    last_user: str,
    messages: list[ChatMessage],
    user_turns: list[str],
) -> str | None:
    folder = _extract_project_folder(last_user)
    if folder:
        return folder
    for m in messages:
        if m.role != "system":
            continue
        found = re.search(r'"pending_deploy_root"\s*:\s*"([^"]+)"', m.content or "")
        if found:
            return found.group(1).strip()
    for turn in reversed(user_turns[:-1] if len(user_turns) > 1 else []):
        f = _extract_project_folder(turn)
        if f:
            return f
    return None


def _resolve_deploy_domain(
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
        found = re.search(r'"pending_deploy_domain"\s*:\s*"([^"]+)"', m.content or "")
        if found:
            return found.group(1).strip().lower()
    for turn in reversed(user_turns[:-1] if len(user_turns) > 1 else []):
        h = _extract_hostname(turn.lower())
        if h:
            return h
    return None


def _django_deploy_active(
    last_user_l: str,
    messages: list[ChatMessage],
    user_turns: list[str],
) -> bool:
    if _wants_django_deploy(last_user_l):
        return True
    pending = _pending_django_deploy(messages, user_turns)
    if not pending:
        return False
    if _extract_project_folder(last_user_l) or _extract_hostname(last_user_l):
        return True
    if _wants_go_ahead(last_user_l):
        return True
    return False


def _django_after_tools(
    messages: list[ChatMessage],
    tool_names: set[str],
    last_user_l: str,
    *,
    user_turns: list[str] | None = None,
) -> ChatResult | None:
    turns = user_turns or []
    if not _django_deploy_active(last_user_l, messages, turns):
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
    if "create_python_app" in names:
        return None
    if not names & {
        "list_domains",
        "list_files",
        "check_application_status",
        "get_deployment_context",
    }:
        return None

    domains: list[dict] = []
    py_apps: list[dict] = []
    file_dirs: list[str] = []
    for m in recent:
        try:
            data = json.loads(m.content or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        name = m.name or ""
        if name == "list_domains":
            domains = _domains_from_tool_payload(data)
        elif name == "check_application_status":
            py_apps, _node = _apps_from_tool_payload(data)
        elif name == "list_files":
            payload = data.get("data") if isinstance(data.get("data"), dict) else data
            if isinstance(payload.get("result"), dict):
                payload = payload["result"]
            entries = (payload or {}).get("entries") or []
            for e in entries:
                if isinstance(e, dict) and e.get("is_dir"):
                    n = str(e.get("name") or "")
                    if n and not n.startswith("."):
                        file_dirs.append(n)

    root = _resolve_deploy_root(last_user_l, messages, turns)
    domain = _resolve_deploy_domain(last_user_l, messages, turns)

    # App déjà présente sur ce root ?
    if root:
        existing = next(
            (
                a
                for a in py_apps
                if str(a.get("relative_root") or a.get("name") or "").strip("/") == root
                or str(a.get("name") or "") == root
            ),
            None,
        )
        if existing:
            aid = int(existing.get("id") or 0)
            return ChatResult(
                content=(
                    f"Le projet **`{root}`** est déjà enregistré comme app "
                    f"**#{aid}** `{existing.get('name')}` ({existing.get('status')}).\n\n"
                    "Je peux **installer les dépendances** puis **démarrer**. "
                    "Dis *installe les deps* ou *démarre l'app*."
                ),
                provider="mock",
                model="mock-coach",
            )

    if root and domain and "create_python_app" in tool_names:
        app_name = re.sub(r"[^a-z0-9_-]", "-", root.lower())[:40] or "django-app"
        return ChatResult(
            content=(
                f"Parfait — projet **`{root}`**, domaine **`{domain}`**.\n"
                "Je prépare **create_python_app** (Django / WSGI) — "
                "clique **Exécuter** pour confirmer."
            ),
            tool_calls=[
                ToolCallRequest(
                    id=str(uuid4()),
                    name="create_python_app",
                    arguments={
                        "name": app_name,
                        "label": app_name,
                        "relative_root": root,
                        "framework": "django",
                        "mode": "wsgi",
                        "python_version": "3.12",
                        "domain_name": domain,
                        "entrypoint": "passenger_wsgi.py",
                    },
                )
            ],
            provider="mock",
            model="mock-coach",
        )

    if root and not domain:
        sample = ", ".join(f"`{d.get('name')}`" for d in domains[:8]) if domains else "(aucun)"
        return ChatResult(
            content=(
                f"Projet détecté : **`{root}`**.\n"
                f"Domaines dispo : {sample}\n\n"
                "Indique le **domaine** (ex. *vzone.7une.info*) et j'enchaîne la création de l'app."
            ),
            provider="mock",
            model="mock-coach",
        )

    if not root:
        dirs = [d for d in file_dirs if d not in {"mail", "ssl", "tmp", "logs", "etc", "domains"}][:12]
        hint = ", ".join(f"`{d}`" for d in dirs) if dirs else "ex. `vzone`"
        return ChatResult(
            content=(
                "Pour déployer Django, j'ai besoin du **dossier projet** (Application root).\n"
                f"Dossiers visibles : {hint}\n\n"
                "Exemple : *le dossier vzone contient le projet* "
                "puis le domaine (*vzone.7une.info*)."
            ),
            provider="mock",
            model="mock-coach",
        )

    return None


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


def _norm_text(text: str) -> str:
    """Minuscules + sans accents pour un matching robuste."""
    import unicodedata

    raw = (text or "").lower().strip()
    return "".join(
        c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn"
    )


def _score_keywords(text_n: str, keywords: dict[str, float]) -> float:
    score = 0.0
    for kw, pts in keywords.items():
        if kw in text_n:
            score += pts
    return score


def _page_help_only(text_n: str) -> bool:
    """True si le message est surtout une demande d'aide contextuelle (vague)."""
    helpish = any(
        k in text_n
        for k in (
            "aide",
            "help",
            "je suis sur",
            "aide-moi",
            "aide moi",
            "que faire",
            "que peux-tu",
            "tu peux m aider",
        )
    )
    if not helpish:
        return False
    topics = (
        "mail",
        "email",
        "messagerie",
        "boite",
        "domaine",
        "ssl",
        "fichier",
        "dossier",
        "wordpress",
        "base",
        "database",
        "cron",
        "backup",
        "sauvegarde",
        "ftp",
        "docker",
        "git",
        "python",
        "node",
        "dns",
        "php",
    )
    return not any(t in text_n for t in topics)


def _intent_from_scores(
    text: str,
    text_n: str,
    *,
    page_sec: str,
    page_runtime: str,
    page_help: bool,
    tool_names: set[str],
) -> dict | None:
    """Choisit l'intent le plus aligné sur le MESSAGE (page = bonus faible seulement)."""
    del page_runtime  # réservé (logs runtime via page plus bas)
    wants_list = any(
        k in text_n
        for k in (
            "liste",
            "lister",
            "list ",
            "montre",
            "montrer",
            "affiche",
            "quels sont",
            "quelles sont",
            "quelles",
            "quels",
            "quelle",
            "quel ",
            "vois mes",
            "voir mes",
            "donne-moi",
            "donne moi",
            "mes ",
            "tourne",
            "tournent",
            "running",
            "en cours",
        )
    )
    createish = any(
        k in text_n
        for k in ("cree", "creer", "ajoute", "ajouter", "nouveau", "nouveua", "installe", "installer")
    )

    candidates: list[tuple[str, float, str, dict]] = []

    def add(intent_id: str, score: float, section: str, payload: dict) -> None:
        if score <= 0:
            return
        if page_help and section and page_sec == section:
            score += 1.5
        candidates.append((intent_id, score, section, payload))

    mail_score = _score_keywords(
        text_n,
        {
            "boites mail": 12,
            "boite mail": 12,
            "comptes mail": 11,
            "compte mail": 10,
            "compte de messagerie": 12,
            "messagerie": 9,
            "mailbox": 9,
            "courriel": 8,
            "e-mail": 8,
            "email": 7,
            "boites": 5,
            "boite": 4,
            "mail": 3,
        },
    )
    if mail_score >= 3:
        if createish and mail_score >= 4:
            addr = _extract_email_address(text)
            say = "Compris — création d'une boîte mail"
            if addr:
                say += f" **{addr[0]}@{addr[1]}**"
            say += ". Je vérifie tes domaines mail…"
            add(
                "create_mailbox",
                mail_score + 8,
                "email",
                {"say": say, "tools": [("list_mailboxes", {})]},
            )
        elif wants_list or mail_score >= 5 or "boite" in text_n or "messagerie" in text_n:
            add(
                "list_mailboxes",
                mail_score + (4 if wants_list else 0),
                "email",
                {
                    "say": "Compris — je liste tes **domaines mail et boîtes**…",
                    "tools": [("list_mailboxes", {})],
                },
            )

    dom_score = _score_keywords(
        text_n, {"domaines": 8, "domaine": 6, "domain": 5, "sous-domaine": 7, "sous domaine": 7}
    )
    ssl_score = _score_keywords(
        text_n, {"ssl": 8, "lets encrypt": 9, "letsencrypt": 9, "certificat": 7, "https": 4}
    )
    if dom_score >= 4 and (wants_list or createish or dom_score >= 6):
        add(
            "list_domains",
            dom_score + (3 if wants_list else 0),
            "domains",
            {"say": "Compris — je liste tes **domaines**…", "tools": [("list_domains", {})]},
        )
    if ssl_score >= 5:
        add(
            "ssl",
            ssl_score,
            "domains",
            {
                "say": "Compris — je regarde tes domaines pour le **SSL**…",
                "tools": [("list_domains", {})],
            },
        )

    wp_score = _score_keywords(
        text_n, {"wordpress": 10, "wordpresse": 10, "sites wp": 9, " wp": 4, "wp ": 4}
    )
    if wp_score >= 4:
        if createish or _wants_wordpress_install(text):
            host = _extract_hostname(text)
            say = "Compris — installation WordPress"
            if host:
                say += f" sur **{host}**"
            say += " — je vérifie domaines et sites WP…"
            add(
                "install_wp",
                wp_score + 10,
                "wordpress",
                {"say": say, "tools": [("list_domains", {}), ("list_wordpress_sites", {})]},
            )
        else:
            add(
                "list_wp",
                wp_score + (3 if wants_list else 0),
                "wordpress",
                {
                    "say": "Compris — je liste tes **sites WordPress**…",
                    "tools": [("list_wordpress_sites", {})],
                },
            )

    file_score = _score_keywords(
        text_n,
        {
            "file manager": 10,
            "fichiers": 8,
            "fichier": 6,
            "dossiers": 7,
            "dossier": 5,
            "repertoire": 6,
            "home": 2,
        },
    )
    if mail_score >= 5:
        file_score -= 20
    if file_score >= 4 and (wants_list or "cherche" in text_n or "trouve" in text_n or createish):
        if "cherche" in text_n or "trouve" in text_n or "search" in text_n:
            q = text.split("cherche")[-1].strip()[:80] if "cherche" in text else ""
            add(
                "search_files",
                file_score + 5,
                "files",
                {
                    "say": "Compris — je cherche dans tes fichiers…",
                    "tools": [("search_account_files", {"query": q or "*", "path": ""})],
                },
            )
        else:
            add(
                "list_files",
                file_score + (3 if wants_list else 0),
                "files",
                {
                    "say": "Compris — je liste le contenu du **home**…",
                    "tools": [("list_files", {"path": ""})],
                },
            )

    db_score = _score_keywords(
        text_n,
        {
            "bases de donnees": 10,
            "base de donnees": 9,
            "databases": 8,
            "database": 7,
            "mysql": 6,
            "postgres": 6,
            "bdd": 6,
            "bases": 4,
        },
    )
    if db_score >= 4 and (wants_list or createish):
        add(
            "list_db",
            db_score + (3 if wants_list else 0),
            "databases",
            {"say": "Compris — je liste tes **bases de données**…", "tools": [("list_databases", {})]},
        )

    cron_score = _score_keywords(text_n, {"cron": 8, "tache planif": 8, "crontab": 7, "planifiee": 4})
    if cron_score >= 4 and wants_list:
        add(
            "list_cron",
            cron_score + 3,
            "cron",
            {"say": "Compris — je liste tes **tâches cron**…", "tools": [("list_cron_jobs", {})]},
        )

    ftp_score = _score_keywords(text_n, {"ftp": 8, "sftp": 6})
    if ftp_score >= 4 and wants_list:
        add(
            "list_ftp",
            ftp_score + 3,
            "ftp",
            {"say": "Compris — je liste tes **comptes FTP**…", "tools": [("list_ftp_accounts", {})]},
        )

    bak_score = _score_keywords(text_n, {"sauvegardes": 9, "sauvegarde": 7, "backups": 8, "backup": 7})
    if bak_score >= 4:
        if createish or "lance" in text_n or "faire un" in text_n:
            add(
                "create_backup",
                bak_score + 6,
                "backups",
                {
                    "say": "Compris — je prépare une **sauvegarde** (confirmation)…",
                    "tools": [("create_backup", {"backup_type": "full"})],
                },
            )
        elif wants_list:
            add(
                "list_backups",
                bak_score + 3,
                "backups",
                {"say": "Compris — je liste tes **sauvegardes**…", "tools": [("list_backups", {})]},
            )

    dns_score = _score_keywords(text_n, {"dns": 8, "zone dns": 9, "enregistrement": 5})
    if dns_score >= 4 and wants_list:
        add(
            "list_dns",
            dns_score + 3,
            "dns",
            {"say": "Compris — je liste tes **zones DNS**…", "tools": [("list_dns_zones", {})]},
        )

    php_score = _score_keywords(text_n, {"php": 6, "selecteur php": 9})
    if php_score >= 5 and wants_list:
        add(
            "list_php",
            php_score + 2,
            "php",
            {
                "say": "Compris — je regarde les versions PHP…",
                "tools": [("list_php_versions", {}), ("list_php_selectors", {})],
            },
        )

    git_score = _score_keywords(text_n, {"git": 6, "depot": 6, "repo": 5, "github": 5})
    if git_score >= 4 and wants_list:
        add(
            "list_git",
            git_score + 3,
            "git",
            {"say": "Compris — je liste tes **dépôts Git**…", "tools": [("list_git_repos", {})]},
        )

    docker_score = _score_keywords(text_n, {"docker": 8, "conteneur": 7, "container": 7})
    if docker_score >= 4 and wants_list:
        add(
            "list_docker",
            docker_score + 3,
            "docker",
            {
                "say": "Compris — je liste tes **conteneurs Docker**…",
                "tools": [("list_docker_containers", {})],
            },
        )

    if any(k in text_n for k in ("kubernetes", "k8s", "kubectl")):
        add("k8s", 10, "", {"say": "Compris — vue **Kubernetes**…", "tools": [("get_k8s_overview", {})]})

    apps_score = _score_keywords(
        text_n,
        {
            "applications": 8,
            "application": 5,
            "apps": 6,
            "python": 4,
            "node": 4,
            "django": 5,
            "flask": 4,
            "fastapi": 4,
            "tourne": 3,
            "tournent": 4,
            "running": 4,
        },
    )
    if "apps" in text_n or re.search(r"\bapps?\b", text_n):
        apps_score = max(apps_score, 6.0)
    if apps_score >= 4 and wants_list:
        add(
            "list_apps",
            apps_score + 3,
            "python" if "python" in text_n or "django" in text_n else ("node" if "node" in text_n else ""),
            {
                "say": "Compris — je liste tes **applications**…",
                "tools": [("check_application_status", {})],
            },
        )

    overview_score = _score_keywords(
        text_n,
        {
            "vue d'ensemble": 10,
            "overview": 8,
            "espace disque": 8,
            "quota": 6,
            "mon package": 8,
            "mon forfait": 7,
        },
    )
    if overview_score >= 5:
        if "package" in text_n or "forfait" in text_n:
            add(
                "package",
                overview_score,
                "package",
                {"say": "Compris — je regarde ton **package**…", "tools": [("get_my_package", {})]},
            )
        else:
            add(
                "overview",
                overview_score,
                "home",
                {
                    "say": "Compris — je charge la **vue d'ensemble**…",
                    "tools": [("get_account_overview", {})],
                },
            )

    if "2fa" in text_n or ("securite" in text_n and "mot de passe" not in text_n):
        add(
            "security",
            8,
            "security",
            {"say": "Compris — statut **sécurité** (lecture)…", "tools": [("get_security_status", {})]},
        )

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    _best_id, best_score, _sec, payload = candidates[0]
    if best_score < 4:
        return None
    tools = payload.get("tools") or []
    if tools and not any(n in tool_names for n, _a in tools):
        return None
    return payload


def _detect_intent(
    last_user_l: str,
    messages: list[ChatMessage],
    tool_names: set[str],
    *,
    user_turns: list[str] | None = None,
) -> dict | None:
    """Intent message-first : le texte utilisateur prime toujours sur la page UI."""
    turns = user_turns or []
    page = _page_meta(messages)
    page_sec = _page_section(page)
    page_runtime = (page.get("runtime") or "").lower()
    text_n = _norm_text(last_user_l)
    page_help = _page_help_only(text_n)

    # Commande jail whitelistée AVANT lifecycle (« lance ls » ≠ start app)
    jail_id = _resolve_jail_command_id(last_user_l)
    if jail_id and "run_jail_command" in tool_names:
        args: dict[str, Any] = {"command_id": jail_id}
        if _jail_needs_app(jail_id):
            app_id = _extract_app_id(last_user_l) or _infer_app_id_from_history(
                messages, last_user_l
            )
            if not app_id:
                return {
                    "say": (
                        f"Compris — commande **{jail_id}** : "
                        "j'ai besoin de l'**id** de l'app. Je liste tes applications…"
                    ),
                    "tools": [("check_application_status", {})],
                }
            args["app_id"] = int(app_id)
            args["runtime"] = (
                _guess_runtime(last_user_l + " " + page_runtime)
                if _guess_runtime(last_user_l + " " + page_runtime) in {"python", "node"}
                else "python"
            )
        return {
            "say": (
                f"Compris — exécution jail **`{jail_id}`** "
                "(confirmation **Exécuter**)…"
            ),
            "tools": [("run_jail_command", args)],
        }

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
                "say": f"Compris — {labels[lifecycle]} de l'app #{app_id} (confirmation)…",
                "tools": [
                    (
                        tool,
                        {
                            "runtime": runtime if runtime in {"python", "node"} else "python",
                            "app_id": app_id,
                        },
                    )
                ],
            }
        return {
            "say": f"Compris — je regarde tes apps pour le {labels[lifecycle]}…",
            "tools": [("check_application_status", {})],
        }

    if _wordpress_flow_active(last_user_l, messages, turns):
        host = _resolve_wp_host(last_user_l, messages, turns)
        say = "Compris — installation WordPress"
        if host:
            say += f" sur **{host}**"
        say += " — je vérifie domaines et sites WP…"
        return {
            "say": say,
            "tools": [("list_domains", {}), ("list_wordpress_sites", {})],
        }

    # Déploiement Django / Python (dossier local multi-tours)
    if _django_deploy_active(last_user_l, messages, turns):
        root = _resolve_deploy_root(last_user_l, messages, turns)
        domain = _resolve_deploy_domain(last_user_l, messages, turns)
        say = "Compris — déploiement **Django/Python**"
        if root:
            say += f" depuis **`{root}`**"
        if domain:
            say += f" → **{domain}**"
        say += ". Je vérifie apps, domaines et fichiers…"
        return {
            "say": say,
            "tools": [
                ("check_application_status", {}),
                ("list_domains", {}),
                ("list_files", {"path": ""}),
            ],
        }

    if _wants_mkdir(last_user_l):
        name = _extract_path_name(last_user_l, kind="dir")
        if name and "mkdir_path" in tool_names:
            return {
                "say": f"Compris — création du dossier **{name}** (confirmation)…",
                "tools": [("mkdir_path", {"path": name})],
            }
        return {"say": "Pour créer un dossier, indique le nom (ex. *crée un dossier logs*)."}
    if _wants_write_file(last_user_l):
        path = _extract_path_name(last_user_l, kind="file")
        if path and "write_file" in tool_names:
            return {
                "say": f"Compris — création du fichier **{path}** (confirmation)…",
                "tools": [
                    (
                        "write_file",
                        {"path": path, "content": _extract_file_content(last_user_l)},
                    )
                ],
            }
        return {
            "say": "Pour créer un fichier, indique le nom (ex. *crée un fichier du nom notes.txt*)."
        }
    if _wants_delete_path(last_user_l):
        path = _extract_path_name(last_user_l, kind="any")
        if path and "delete_paths" in tool_names:
            return {
                "say": f"Compris — suppression de **{path}** (confirmation)…",
                "tools": [("delete_paths", {"paths": [path]})],
            }

    scored = _intent_from_scores(
        last_user_l,
        text_n,
        page_sec=page_sec,
        page_runtime=page_runtime,
        page_help=page_help and len(text_n) < 120,
        tool_names=tool_names,
    )
    if scored:
        return scored

    if page_help or (
        any(k in text_n for k in ("aide", "help", "je suis sur")) and len(text_n) < 100
    ):
        page_defaults = {
            "email": (
                "Tu es sur Email. Je liste tes boîtes.",
                [("list_mailboxes", {})],
            ),
            "ftp": ("Tu es sur FTP. Je liste tes comptes…", [("list_ftp_accounts", {})]),
            "cron": ("Tu es sur Cron. Je liste tes tâches…", [("list_cron_jobs", {})]),
            "backups": ("Tu es sur Backups. Je liste tes sauvegardes…", [("list_backups", {})]),
            "files": ("Tu es sur File Manager. Je liste le home…", [("list_files", {"path": ""})]),
            "domains": ("Tu es sur Domaines. Je liste tes domaines…", [("list_domains", {})]),
            "databases": ("Tu es sur Databases. Je liste tes bases…", [("list_databases", {})]),
            "dns": ("Tu es sur DNS. Je liste tes zones…", [("list_dns_zones", {})]),
            "wordpress": (
                "Tu es sur WordPress. Je liste tes sites.",
                [("list_wordpress_sites", {})],
            ),
            "python": (
                "Tu es sur Python. Je regarde statut et logs…",
                [
                    ("check_application_status", {}),
                    ("get_page_logs", {"runtime": "python", "lines": 100}),
                    ("analyze_deployment_error", {"runtime": "python"}),
                ],
            ),
            "node": (
                "Tu es sur Node. Je regarde statut et logs…",
                [
                    ("check_application_status", {}),
                    ("get_page_logs", {"runtime": "node", "lines": 100}),
                ],
            ),
        }
        if page_sec in page_defaults:
            say, tools = page_defaults[page_sec]
            return {"say": say, "tools": tools}

    if any(k in text_n for k in ("log", "erreur", "error", "failed", "echou", "traceback")):
        rt = _guess_runtime(last_user_l + " " + page_runtime)
        return {
            "say": "Compris — je récupère les **logs**…",
            "tools": [
                ("get_deployment_logs", {"runtime": rt, "lines": 80}),
                ("analyze_deployment_error", {"runtime": rt}),
            ],
        }

    if (
        "jail" in text_n
        or (
            "commande" in text_n
            and any(k in text_n for k in ("liste", "dispo", "autoris", "catalogue", "whitelist"))
        )
    ) and not _resolve_jail_command_id(last_user_l):
        return {
            "say": "Compris — catalogue des commandes jail…",
            "tools": [("list_jail_commands", {})],
        }

    # Vue compte vague uniquement — jamais si le message cible déjà une ressource
    topicish = any(
        k in text_n
        for k in (
            "app",
            "python",
            "node",
            "django",
            "mail",
            "messagerie",
            "boite",
            "email",
            "domaine",
            "ssl",
            "fichier",
            "dossier",
            "base",
            "bdd",
            "ftp",
            "cron",
            "docker",
            "git",
            "wordpress",
            "wp",
            "sauvegarde",
            "backup",
        )
    )
    vague_account = any(
        k in text_n
        for k in (
            "contexte",
            "ce que j'ai",
            "ce que j ai",
            "resume de mon compte",
            "resume mon compte",
            "vue d'ensemble",
            "vue densemble",
        )
    ) or ("sur mon compte" in text_n and not topicish and len(text_n) < 80)
    if vague_account and not topicish:
        return {
            "say": "Compris — je charge la **vue d'ensemble** du compte…",
            "tools": [
                ("get_account_overview", {}),
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
            # Si on a déjà la liste d'apps, le contexte déploiement est redondant
            if "check_application_status" not in {(x.name or "") for x in tool_msgs}:
                formatted = _format_context(name, data)
                if formatted:
                    parts.append(formatted)
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
            # Avec une liste d'apps, n'affiche pas le dump quota/usage
            if "check_application_status" not in {(x.name or "") for x in tool_msgs}:
                parts.append(_format_overview(data))
        elif name == "run_jail_command":
            payload = _payload(data)
            out = str(payload.get("stdout") or payload.get("output") or "").strip()
            err = str(payload.get("stderr") or "").strip()
            cid = payload.get("command_id") or "commande"
            if data.get("pending_confirmation"):
                parts.append(
                    f"Commande jail **`{cid}`** en attente de confirmation "
                    "(bouton **Exécuter**)."
                )
            elif data.get("ok"):
                body = out or "(sortie vide)"
                extra = f"\nstderr:\n{err}" if err else ""
                parts.append(f"**`{cid}`** :\n```\n{body[:2000]}{extra}\n```")
            else:
                parts.append(f"**`{cid}`** échoué : {data.get('error') or err or 'erreur'}")
        elif name == "list_jail_commands":
            payload = _payload(data)
            cmds = payload.get("commands") or []
            lines = ["**Commandes jail autorisées**", ""]
            for c in cmds[:30]:
                if isinstance(c, dict):
                    lines.append(
                        f"- `{c.get('id')}` — {c.get('label') or c.get('description') or ''}"
                    )
            parts.append("\n".join(lines) if len(lines) > 2 else "Aucune commande jail.")
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
    """Résumé lisible — jamais la liste brute des clés JSON."""
    del name
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict):
        return ""
    ctx = payload.get("context") if isinstance(payload.get("context"), dict) else payload
    if not isinstance(ctx, dict):
        return ""
    bits: list[str] = []
    for key, label in (
        ("python_apps", "apps Python"),
        ("node_apps", "apps Node"),
        ("domains", "domaines"),
        ("databases", "bases"),
        ("git_repos", "repos Git"),
    ):
        val = ctx.get(key)
        if isinstance(val, list):
            bits.append(f"{label}={len(val)}")
        elif val is not None and not isinstance(val, dict):
            bits.append(f"{label}={val}")
    if bits:
        return f"**Contexte déploiement** — {', '.join(bits)}."
    return ""


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

    if url or any(k in low for k in ("github",)):
        return (
            "Repo noté"
            + (f" (`{url}`)" if url else "")
            + ". Pour Django/Python, dis plutôt : "
            "*déploie Django depuis le dossier … sur domaine.tld* "
            "— sinon donne le dossier local + le domaine cible."
        )

    # Multi-tours / fallback : toujours refléter le message, proposer l'action la plus proche
    hint = ""
    tn = _norm_text(low)
    if any(k in tn for k in ("mail", "boite", "messagerie", "email")):
        hint = "Ex. *liste mes boîtes mail* ou *crée contact@domaine.tld mot de passe …*"
    elif any(k in tn for k in ("django", "deploy", "deployer", "deploie", "flask", "fastapi")):
        hint = (
            "Ex. *déploie Django depuis le dossier vzone sur vzone.7une.info* "
            "— je crée l'app et demande confirmation."
        )
    elif any(k in tn for k in ("fichier", "dossier", "repertoire")):
        hint = "Ex. *liste mes fichiers* ou *crée un fichier du nom notes.txt*"
    elif any(k in tn for k in ("domaine", "ssl", "wordpress", "wp")):
        hint = "Ex. *liste mes domaines* / *liste mes sites WordPress*"
    elif any(k in tn for k in ("app", "python", "node")):
        hint = "Ex. *liste mes applications* ou *arrête l'app #ID*"
    else:
        hint = "Ex. *liste mes domaines*, *mes mails*, *mes apps*…"

    return (
        f"J'ai bien lu : « {text[:240]} ».\n\n"
        "Reformule en une action claire du panneau et j'exécute tout de suite.\n"
        f"{hint}"
    )
