"""Helpers partagés pour les tools IA (ownership, erreurs, sérialisation sûre)."""
from __future__ import annotations

from typing import Any, Callable

from apps.accounts.models import User
from apps.ai_assistant.services.redaction import redact_obj
from apps.core.exceptions import VZoneAPIException


def ok(**data: Any) -> dict[str, Any]:
    return {"ok": True, **redact_obj(data)}


def err(message: str, code: str = "tool_error") -> dict[str, Any]:
    return {"ok": False, "error": str(message)[:500], "code": code}


def run_service(fn: Callable[[], Any]) -> dict[str, Any]:
    """Exécute un service et normalise VZoneAPIException → err()."""
    try:
        result = fn()
        if isinstance(result, dict) and "ok" in result:
            return redact_obj(result)
        if result is None:
            return ok()
        return ok(result=result if not isinstance(result, dict) else result)
    except VZoneAPIException as exc:
        return err(str(exc.detail), getattr(exc, "default_code", None) or "error")
    except Exception as exc:  # noqa: BLE001
        return err(str(exc))


def require_int(params: dict[str, Any], key: str) -> int | None:
    raw = params.get(key)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def require_str(params: dict[str, Any], key: str, *, default: str = "", max_len: int = 500) -> str:
    return str(params.get(key) or default).strip()[:max_len]


PENDING_DESCRIPTIONS: dict[str, str] = {
    "restart_application": "Redémarrer l'application",
    "stop_application": "Arrêter l'application",
    "start_application": "Démarrer l'application",
    "install_dependencies": "Installer les dépendances",
    "deploy_application": "Déployer (git pull) le dépôt",
    "create_python_app_from_git": "Créer app Python depuis Git",
    "create_node_app_from_git": "Créer app Node depuis Git",
    "create_python_app": "Créer une application Python",
    "update_python_app": "Mettre à jour une application Python",
    "delete_python_app": "Supprimer une application Python",
    "create_node_app": "Créer une application Node",
    "update_node_app": "Mettre à jour une application Node",
    "delete_node_app": "Supprimer une application Node",
    "create_domain": "Créer un domaine / sous-domaine",
    "delete_domain": "Supprimer un domaine",
    "create_redirect": "Créer une redirection",
    "issue_ssl_certificate": "Émettre un certificat Let's Encrypt",
    "create_database": "Créer une base de données",
    "delete_database": "Supprimer une base de données",
    "create_db_user": "Créer un utilisateur de base",
    "delete_db_user": "Supprimer un utilisateur de base",
    "grant_db_privilege": "Accorder des privilèges DB",
    "revoke_db_privilege": "Révoquer des privilèges DB",
    "create_cron_job": "Créer une tâche cron",
    "update_cron_job": "Modifier une tâche cron",
    "delete_cron_job": "Supprimer une tâche cron",
    "sync_cron_jobs": "Synchroniser le crontab",
    "install_wordpress": "Installer WordPress",
    "delete_wordpress": "Supprimer WordPress",
    "list_files": "Lister des fichiers",
    "mkdir_path": "Créer un dossier",
    "write_file": "Écrire un fichier",
    "delete_paths": "Supprimer des fichiers/dossiers",
    "rename_path": "Renommer un fichier/dossier",
    "move_paths": "Déplacer des fichiers",
    "copy_paths": "Copier des fichiers",
    "chmod_path": "Changer les permissions",
    "compress_files": "Compresser des fichiers",
    "decompress_archive": "Décompresser une archive",
    "create_ftp_account": "Créer un compte FTP",
    "update_ftp_account": "Modifier un compte FTP",
    "suspend_ftp_account": "Suspendre/réactiver un compte FTP",
    "delete_ftp_account": "Supprimer un compte FTP",
    "create_backup": "Lancer une sauvegarde",
    "restore_backup": "Restaurer une sauvegarde",
    "delete_backup": "Supprimer une sauvegarde",
    "upsert_backup_schedule": "Créer/modifier une planification backup",
    "delete_backup_schedule": "Supprimer une planification backup",
    "create_mailbox": "Créer une boîte mail",
    "update_mailbox": "Modifier une boîte mail",
    "suspend_mailbox": "Suspendre/réactiver une boîte mail",
    "delete_mailbox": "Supprimer une boîte mail",
    "create_mail_forwarder": "Créer un forwarder email",
    "enable_dkim": "Activer DKIM",
    "sync_mail_dns": "Synchroniser DNS mail",
    "create_dns_zone": "Créer une zone DNS",
    "upsert_dns_record": "Créer/modifier un enregistrement DNS",
    "delete_dns_record": "Supprimer un enregistrement DNS",
    "toggle_dnssec": "Activer/désactiver DNSSEC",
    "create_php_selector": "Créer un sélecteur PHP",
    "update_php_selector": "Modifier un sélecteur PHP",
    "delete_php_selector": "Supprimer un sélecteur PHP",
    "clone_git_repository": "Cloner un dépôt Git",
    "run_git_deploy_script": "Exécuter le script de déploiement Git",
    "generate_git_deploy_key": "Générer une clé de déploiement Git",
    "delete_git_repository": "Supprimer un dépôt Git",
    "create_docker_container": "Créer un conteneur Docker",
    "start_docker_container": "Démarrer un conteneur Docker",
    "stop_docker_container": "Arrêter un conteneur Docker",
    "restart_docker_container": "Redémarrer un conteneur Docker",
    "remove_docker_container": "Supprimer un conteneur Docker",
    "apply_k8s_manifest": "Appliquer un manifeste Kubernetes",
    "delete_k8s_manifest": "Supprimer des ressources Kubernetes",
}


def pending_description(tool_name: str, params: dict[str, Any] | None = None) -> str:
    params = params or {}
    if tool_name == "run_jail_command":
        return f"Commande jail whitelistée `{params.get('command_id')}` (UID client)"
    base = PENDING_DESCRIPTIONS.get(tool_name, tool_name)
    # Enrichit avec un id/nom si présent
    for key in ("name", "domain_name", "path", "address", "command_id"):
        if params.get(key):
            return f"{base} — {params[key]}"
    for key in ("app_id", "domain_id", "db_id", "job_id", "archive_id", "container_id", "repo_id"):
        if params.get(key):
            return f"{base} (id {params[key]})"
    return base
