"""Playbooks de déploiement guidés (checklist UI)."""
from __future__ import annotations

from typing import Any


PLAYBOOKS: list[dict[str, Any]] = [
    {
        "id": "django-github",
        "title": "Django depuis GitHub",
        "runtime": "python",
        "icon": "django",
        "prompt": (
            "Je veux déployer mon application Django depuis GitHub. "
            "Guide-moi étape par étape et demande ce qui manque "
            "(URL repo, branche, version Python, domaine, base de données)."
        ),
        "steps": [
            {"id": "repo", "label": "Dépôt Git (URL + branche)"},
            {"id": "runtime", "label": "Version Python"},
            {"id": "domain", "label": "Domaine cible"},
            {"id": "database", "label": "Base de données (optionnel)"},
            {"id": "env", "label": "Variables d'environnement (noms)"},
            {"id": "clone", "label": "Clone / pull Git"},
            {"id": "app", "label": "Créer l'app Python"},
            {"id": "deps", "label": "Installer les dépendances"},
            {"id": "start", "label": "Démarrer / vérifier"},
        ],
    },
    {
        "id": "node-github",
        "title": "Node.js depuis Git",
        "runtime": "node",
        "icon": "node",
        "prompt": (
            "Je veux déployer une application Node.js depuis Git. "
            "Demande repo, branche, script start (npm), domaine, puis guide le déploiement."
        ),
        "steps": [
            {"id": "repo", "label": "Dépôt Git"},
            {"id": "runtime", "label": "Version Node / script start"},
            {"id": "domain", "label": "Domaine"},
            {"id": "clone", "label": "Clone Git"},
            {"id": "app", "label": "Créer l'app Node"},
            {"id": "deps", "label": "npm install"},
            {"id": "start", "label": "Démarrer"},
        ],
    },
    {
        "id": "diagnose-logs",
        "title": "Diagnostiquer une erreur",
        "runtime": "any",
        "icon": "bug",
        "prompt": (
            "Analyse mes logs de déploiement, détecte le problème (ex. ModuleNotFoundError), "
            "explique la cause et propose une correction avec action confirmable."
        ),
        "steps": [
            {"id": "status", "label": "Statut des apps"},
            {"id": "logs", "label": "Récupérer les logs"},
            {"id": "analyze", "label": "Analyser l'erreur"},
            {"id": "fix", "label": "Proposer / confirmer le correctif"},
        ],
    },
    {
        "id": "wordpress",
        "title": "WordPress",
        "runtime": "php",
        "icon": "wp",
        "prompt": (
            "Je veux installer WordPress. Liste mes domaines, aide-moi à choisir, "
            "puis prépare install_wordpress (confirmation) et propose le SSL."
        ),
        "steps": [
            {"id": "domain", "label": "Choisir / vérifier le domaine"},
            {"id": "web", "label": "Stack web"},
            {"id": "install", "label": "Installation WordPress"},
            {"id": "ssl", "label": "SSL (optionnel)"},
        ],
    },
    {
        "id": "ssl-letsencrypt",
        "title": "SSL Let's Encrypt",
        "runtime": "any",
        "icon": "ssl",
        "prompt": (
            "Je veux un certificat SSL Let's Encrypt. Liste mes domaines, "
            "demande lequel, puis prépare issue_ssl_certificate avec confirmation."
        ),
        "steps": [
            {"id": "domain", "label": "Choisir le domaine"},
            {"id": "dns", "label": "Vérifier DNS / A"},
            {"id": "ssl", "label": "Émettre le certificat"},
            {"id": "status", "label": "Vérifier le statut SSL"},
        ],
    },
    {
        "id": "backup-now",
        "title": "Sauvegarde compte",
        "runtime": "any",
        "icon": "backup",
        "prompt": (
            "Montre mes sauvegardes existantes puis propose de lancer une sauvegarde complète "
            "(create_backup) avec confirmation."
        ),
        "steps": [
            {"id": "list", "label": "Lister les backups"},
            {"id": "create", "label": "Lancer une sauvegarde"},
            {"id": "status", "label": "Suivre le statut"},
        ],
    },
    {
        "id": "email-mailbox",
        "title": "Boîte email",
        "runtime": "any",
        "icon": "mail",
        "prompt": (
            "Je veux gérer mes emails. Liste mes boîtes mail et guide-moi pour en créer une "
            "(sans afficher le mot de passe)."
        ),
        "steps": [
            {"id": "list", "label": "Lister domaines / mailboxes"},
            {"id": "create", "label": "Créer une boîte"},
            {"id": "dns", "label": "DKIM / DNS mail (optionnel)"},
        ],
    },
]


def list_playbooks() -> list[dict[str, Any]]:
    return PLAYBOOKS


def get_playbook(playbook_id: str) -> dict[str, Any] | None:
    for item in PLAYBOOKS:
        if item["id"] == playbook_id:
            return item
    return None
