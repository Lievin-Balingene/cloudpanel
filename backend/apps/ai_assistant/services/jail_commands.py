"""Commandes jail whitelistées (pas de shell libre)."""
from __future__ import annotations

from typing import Any

# argv figés — le modèle ne choisit que l'id (+ app_id si besoin)
JAIL_COMMANDS: dict[str, dict[str, Any]] = {
    "pwd": {
        "label": "Répertoire courant (home)",
        "description": "Affiche le répertoire de travail du compte jailé.",
        "argv": ["pwd"],
        "needs_app": False,
    },
    "ls_home": {
        "label": "Lister le home",
        "description": "ls -la du home client.",
        "argv": ["ls", "-la"],
        "needs_app": False,
    },
    "python_version": {
        "label": "Version Python système",
        "description": "python3 --version",
        "argv": ["python3", "--version"],
        "needs_app": False,
    },
    "node_version": {
        "label": "Version Node.js",
        "description": "node -v",
        "argv": ["node", "-v"],
        "needs_app": False,
    },
    "npm_version": {
        "label": "Version npm",
        "description": "npm -v",
        "argv": ["npm", "-v"],
        "needs_app": False,
    },
    "df_home": {
        "label": "Espace disque",
        "description": "df -h .",
        "argv": ["df", "-h", "."],
        "needs_app": False,
    },
    "ls_app": {
        "label": "Lister le dossier de l'app",
        "description": "ls -la du relative_root de l'app (Python ou Node).",
        "argv": ["ls", "-la", "{app_root}"],
        "needs_app": True,
    },
    "du_app": {
        "label": "Taille du dossier app",
        "description": "du -sh de l'app",
        "argv": ["du", "-sh", "{app_root}"],
        "needs_app": True,
    },
    "tail_error_log": {
        "label": "Tail logs/error.log de l'app",
        "description": "Dernières lignes error.log via jail (UID client).",
        "argv": ["tail", "-n", "100", "{app_root}/logs/error.log"],
        "needs_app": True,
    },
    "tail_access_log": {
        "label": "Tail logs/access.log de l'app",
        "description": "Dernières lignes access.log via jail.",
        "argv": ["tail", "-n", "80", "{app_root}/logs/access.log"],
        "needs_app": True,
    },
    "pip_freeze_venv": {
        "label": "pip freeze (venv app Python)",
        "description": "Liste les packages du venv de l'app Python.",
        "argv": ["{venv_python}", "-m", "pip", "freeze"],
        "needs_app": True,
        "runtime": "python",
    },
}


def list_jail_catalog() -> list[dict[str, Any]]:
    out = []
    for cid, meta in JAIL_COMMANDS.items():
        out.append(
            {
                "id": cid,
                "label": meta["label"],
                "description": meta["description"],
                "needs_app": bool(meta.get("needs_app")),
                "runtime": meta.get("runtime") or "",
            }
        )
    return out


def get_jail_command(command_id: str) -> dict[str, Any] | None:
    return JAIL_COMMANDS.get(command_id)
