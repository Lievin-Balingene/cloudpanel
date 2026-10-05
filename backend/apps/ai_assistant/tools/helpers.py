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
        detail = exc.detail
        if isinstance(detail, (list, tuple)) and detail:
            detail = detail[0]
        return err(str(detail), getattr(exc, "default_code", None) or "error")
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        return err(
            f"Paramètre ou donnée invalide ({type(exc).__name__}: {exc})",
            "invalid_params",
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).strip() or type(exc).__name__
        if "string index out of range" in msg.lower():
            return err("Paramètre ou chemin invalide (index).", "invalid_params")
        return err(msg)



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


def resolve_owner(actor: User, params: dict[str, Any] | None = None) -> User:
    """Résout le compte cible (client) pour un tool.

    - Client : toujours lui-même (ignore username étranger).
    - Admin : peut cibler n'importe quel compte via ``username`` / ``account``.
    - Revendeur : uniquement ses clients (parent=revendeur) ou lui-même.
    """
    params = params or {}
    raw = require_str(params, "username") or require_str(params, "account")
    if not raw:
        return actor

    key = raw.lower()
    if actor.role == User.Role.CLIENT:
        own = {
            (actor.username or "").lower(),
            (getattr(actor, "system_username", None) or "").lower(),
        }
        if key not in own:
            raise VZoneAPIException(
                detail="Un client ne peut cibler que son propre compte.",
                code="forbidden_account",
                status_code=403,
            )
        return actor

    target = (
        User.objects.filter(username__iexact=raw).first()
        or User.objects.filter(system_username__iexact=raw).first()
    )
    if target is None:
        raise VZoneAPIException(
            detail=f"Compte introuvable: {raw}",
            code="account_not_found",
            status_code=404,
        )

    if actor.role == User.Role.ADMINISTRATOR:
        return target

    if actor.role == User.Role.RESELLER:
        if target.pk == actor.pk or target.parent_id == actor.pk:
            return target
        raise VZoneAPIException(
            detail="Ce compte client n'appartient pas à votre revendeur.",
            code="forbidden_account",
            status_code=403,
        )

    return actor


def strip_account_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """Retire username/account des params avant l'appel handler métier."""
    data = dict(params or {})
    data.pop("username", None)
    data.pop("account", None)
    return data


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
    "beautify_wordpress_site": "Améliorer le design WordPress",
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
    "set_working_account": "Cibler un compte client",
    "clear_working_account": "Revenir au compte courant",
    "add_ssh_key": "Ajouter une clé SSH",
    "delete_ssh_key": "Supprimer une clé SSH",
    "block_client_ip": "Bloquer une IP (compte)",
    "unblock_client_ip": "Débloquer une IP (compte)",
    "enable_directory_privacy": "Protéger un dossier (.htpasswd)",
    "disable_directory_privacy": "Retirer la protection dossier",
    "delete_redirect": "Supprimer une redirection",
    "delete_mail_forwarder": "Supprimer un forwarder email",
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


CRITICAL_TOOLS = frozenset(
    {
        "delete_domain",
        "delete_database",
        "delete_db_user",
        "delete_email_account",
        "delete_ftp_account",
        "delete_python_app",
        "delete_node_app",
        "delete_php_selector",
        "delete_file",
        "restore_backup",
        "delete_k8s_manifest",
        "remove_docker_container",
        "delete_git_repo",
    }
)
HIGH_TOOLS = frozenset(
    {
        "restart_application",
        "stop_application",
        "run_jail_command",
        "apply_k8s_manifest",
        "write_file",
        "issue_ssl_certificate",
        "install_wordpress",
        "beautify_wordpress_site",
    }
)


def action_risk(tool_name: str, params: dict[str, Any] | None = None) -> str:
    """Niveau de risque pour l'UI Command Approval : low | medium | high | critical."""
    params = params or {}
    name = (tool_name or "").strip()
    if name in CRITICAL_TOOLS or name.startswith("delete_") or name.startswith("terminate"):
        return "critical"
    if name in HIGH_TOOLS or "restart" in name or "stop" in name:
        return "high"
    if name == "run_jail_command":
        cid = str(params.get("command_id") or "")
        if any(x in cid for x in ("rm", "kill", "chmod", "chown", "restart")):
            return "high"
        return "medium"
    return "medium"


def action_command_preview(tool_name: str, params: dict[str, Any] | None = None) -> str:
    """Aperçu type commande proposée pour l'approbation."""
    params = params or {}
    if tool_name == "run_jail_command":
        return f"jail:{params.get('command_id') or '?'}"
    if tool_name == "restart_application":
        return f"systemctl restart app#{params.get('app_id') or '?'}"
    parts = [tool_name]
    for key in ("name", "domain_name", "path", "command_id", "address"):
        if params.get(key):
            parts.append(str(params[key]))
            break
    return " ".join(parts)
