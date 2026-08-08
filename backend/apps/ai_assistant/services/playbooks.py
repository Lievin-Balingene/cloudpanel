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
            "Je veux installer WordPress. Demande le domaine et oriente-moi vers "
            "le module WordPress du panel ; vérifie domaines et stack web."
        ),
        "steps": [
            {"id": "domain", "label": "Choisir / vérifier le domaine"},
            {"id": "web", "label": "Stack web"},
            {"id": "install", "label": "Installation WordPress (module panel)"},
            {"id": "ssl", "label": "SSL (optionnel)"},
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
