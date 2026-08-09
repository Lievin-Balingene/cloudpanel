"""Contexte UI (page courante) → besoin immédiat de l'assistant."""
from __future__ import annotations

from typing import Any


PAGE_CATALOG: dict[str, dict[str, Any]] = {
    "home": {
        "label": "Accueil panel",
        "need": "Vue d'ensemble du compte ; proposer un playbook de déploiement.",
        "suggested_tools": ["get_deployment_context", "check_application_status"],
        "auto_prompt": "Je suis sur l'accueil. Donne-moi un aperçu de mon compte et ce que je peux déployer.",
    },
    "python": {
        "label": "Applications Python",
        "need": "Statut apps Python, logs d'erreur, dépendances, redémarrage.",
        "suggested_tools": [
            "check_application_status",
            "get_deployment_logs",
            "analyze_deployment_error",
            "check_python_version",
        ],
        "auto_prompt": (
            "Je suis sur la page Setup Python App. "
            "Vérifie le statut de mes apps Python, lis les logs récents et dis-moi s'il y a une erreur."
        ),
        "runtime": "python",
    },
    "node": {
        "label": "Applications Node.js",
        "need": "Statut apps Node, logs, npm install, redémarrage.",
        "suggested_tools": [
            "check_application_status",
            "get_deployment_logs",
            "analyze_deployment_error",
            "check_node_version",
        ],
        "auto_prompt": (
            "Je suis sur la page Node.js. "
            "Vérifie le statut, lis les logs et signale les erreurs."
        ),
        "runtime": "node",
    },
    "git": {
        "label": "Git Version Control",
        "need": "Dépôts, pull/deploy, erreurs clone, scripts de déploiement.",
        "suggested_tools": ["get_deployment_context", "deploy_application"],
        "auto_prompt": (
            "Je suis sur Git Version Control. "
            "Montre mes dépôts et propose le prochain déploiement si une erreur existe."
        ),
    },
    "domains": {
        "label": "Domaines",
        "need": "Configuration domaines, SSL, routage web.",
        "suggested_tools": ["check_domain_configuration", "check_web_server"],
        "auto_prompt": "Je suis sur Domaines. Vérifie ma configuration domaines et le serveur web.",
    },
    "dns": {
        "label": "Zone DNS",
        "need": "Zones DNS, records.",
        "suggested_tools": ["check_domain_configuration"],
        "auto_prompt": "Je suis sur Zone Editor DNS. Résume mes domaines et points d'attention DNS.",
    },
    "databases": {
        "label": "Bases de données",
        "need": "MySQL/PostgreSQL du compte.",
        "suggested_tools": ["check_database"],
        "auto_prompt": "Je suis sur Databases. Liste mes bases (sans secrets) et conseils de connexion app.",
    },
    "wordpress": {
        "label": "WordPress",
        "need": "Installation / sites WP.",
        "suggested_tools": ["list_wordpress_sites", "list_domains"],
        "auto_prompt": (
            "Je suis sur WordPress. Liste mes sites. "
            "Pour installer : indique un sous-domaine (ex. crée WordPress sur wp.exemple.com)."
        ),
    },
    "files": {
        "label": "File Manager",
        "need": "Fichiers home, permissions, logs fichiers.",
        "suggested_tools": ["run_jail_command", "list_jail_commands"],
        "auto_prompt": "Je suis sur File Manager. Liste mon home (commande jail autorisée) et indique les dossiers utiles.",
    },
    "terminal": {
        "label": "Terminal SSH",
        "need": "Commandes jail contrôlées avec confirmation.",
        "suggested_tools": ["list_jail_commands", "run_jail_command"],
        "auto_prompt": (
            "Je suis sur le Terminal. "
            "Liste les commandes jail autorisées et propose un diagnostic (versions, logs)."
        ),
    },
    "docker": {
        "label": "Docker",
        "need": "Conteneurs du compte.",
        "suggested_tools": ["get_deployment_context"],
        "auto_prompt": "Je suis sur Docker. Aide-moi à comprendre l'état de mes conteneurs.",
    },
    "backups": {
        "label": "Backups",
        "need": "Sauvegardes / restauration.",
        "suggested_tools": ["get_server_info"],
        "auto_prompt": "Je suis sur Backups. Explique comment vérifier mes sauvegardes.",
    },
    "email": {
        "label": "Email",
        "need": "Comptes mail.",
        "suggested_tools": ["list_mailboxes", "create_mailbox"],
        "auto_prompt": (
            "Je suis sur la page Email. Comptes mail. Aide-moi. "
            "Liste mes boîtes ; pour créer indique adresse + mot de passe."
        ),
    },
    "ftp": {
        "label": "FTP",
        "need": "Comptes FTP.",
        "suggested_tools": ["list_ftp_accounts", "create_ftp_account"],
        "auto_prompt": "Je suis sur FTP. Liste mes comptes FTP.",
    },
    "cron": {
        "label": "Cron Jobs",
        "need": "Tâches planifiées.",
        "suggested_tools": ["list_cron_jobs", "create_cron_job"],
        "auto_prompt": "Je suis sur Cron Jobs. Liste mes tâches planifiées.",
    },
    "php": {
        "label": "PHP Version",
        "need": "Sélecteur PHP.",
        "suggested_tools": ["list_php_versions", "list_php_selectors"],
        "auto_prompt": "Je suis sur Select PHP Version. Conseils de version pour mes sites.",
    },
    "security": {
        "label": "Sécurité / 2FA",
        "need": "Sécurité compte.",
        "suggested_tools": ["get_security_status"],
        "auto_prompt": "Je suis sur Sécurité. Rappels 2FA et bonnes pratiques.",
    },
    "package": {
        "label": "Package / quotas",
        "need": "Ressources du package.",
        "suggested_tools": ["get_my_package", "get_account_overview"],
        "auto_prompt": "Je suis sur Mon package. Résume ce que mon package autorise pour déployer.",
    },
}


def section_from_path(path: str) -> str:
    p = (path or "").strip().lower()
    # /panel/python, /whm/python, /panel/files/upload
    parts = [x for x in p.split("/") if x]
    if not parts:
        return "home"
    # panel|whm , section, ...
    if parts[0] in {"panel", "whm"} and len(parts) == 1:
        return "home"
    if len(parts) >= 2:
        sec = parts[1]
        if sec == "files":
            return "files"
        if sec in PAGE_CATALOG:
            return sec
    return "home"


def normalize_ui_context(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    path = str(data.get("path") or "")[:200]
    section = str(data.get("section") or section_from_path(path))[:64]
    meta = PAGE_CATALOG.get(section) or PAGE_CATALOG["home"]
    portal = str(data.get("portal") or ("whm" if path.startswith("/whm") else "client"))[:16]
    return {
        "path": path,
        "section": section,
        "portal": portal,
        "label": meta["label"],
        "need": meta["need"],
        "suggested_tools": list(meta.get("suggested_tools") or []),
        "runtime": meta.get("runtime") or "",
        "auto_prompt": meta.get("auto_prompt") or "",
    }


def describe_ui_context(ui: dict[str, Any]) -> str:
    runtime = ui.get("runtime") or ""
    lines = [
        f"Page actuelle: {ui.get('label')} ({ui.get('path')})",
        f"Portail: {ui.get('portal')}",
        f"Besoin immédiat: {ui.get('need')}",
        f"Tools suggérées: {', '.join(ui.get('suggested_tools') or [])}",
        f"Runtime page: {runtime or 'n/a'}",
        "Adapte ta première réponse à cette page.",
        "IMPORTANT: le message utilisateur prime toujours sur cette page.",
    ]
    if runtime in {"python", "node"}:
        lines.append(
            "Si des logs sont pertinents, appelle get_deployment_logs / "
            "analyze_deployment_error immédiatement."
        )
    return "\n".join(lines)
