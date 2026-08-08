"""Tools Git deploy (clone, deploy script, clé publique, delete)."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


def _repo_summary(repo, *, include_public_key: bool = False) -> dict[str, Any]:
    data = {
        "id": repo.pk,
        "name": repo.name,
        "label": repo.label or "",
        "remote_url": repo.remote_url,
        "branch": repo.branch,
        "relative_path": repo.relative_path,
        "deploy_script": repo.deploy_script or "",
        "auto_deploy": repo.auto_deploy,
        "status": repo.status,
        "last_commit": repo.last_commit or "",
        "last_commit_message": (repo.last_commit_message or "")[:200],
    }
    if include_public_key:
        data["deploy_key_public"] = repo.deploy_key_public or ""
    return data


@register_tool(
    name="list_git_repos",
    description="Liste les dépôts Git du compte (sans clés privées).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_git_repos(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.git_deploy.services import overview_for, repos_qs

    repos = [_repo_summary(r) for r in repos_qs(user)[:80]]
    return ok(overview=overview_for(user), repositories=repos)


@register_tool(
    name="clone_git_repository",
    description=(
        "Crée et clone un dépôt Git (ou reclône un dépôt existant via repo_id). "
        "Confirmation requise. Ne renvoie jamais la clé privée."
    ),
    parameters={
        "type": "object",
        "properties": {
            "repo_id": {"type": "integer", "description": "Si fourni : reclône le dépôt existant"},
            "name": {"type": "string"},
            "remote_url": {"type": "string"},
            "branch": {"type": "string"},
            "relative_path": {"type": "string"},
            "deploy_script": {"type": "string"},
            "auto_deploy": {"type": "boolean"},
            "label": {"type": "string"},
            "notes": {"type": "string"},
            "clone_now": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    dangerous=True,
)
def clone_git_repository(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.git_deploy.services import clone_repository, create_repository, repos_qs

    repo_id = require_int(params, "repo_id")
    if repo_id:
        repo = repos_qs(user).filter(pk=repo_id).first()
        if not repo:
            return err("Dépôt Git introuvable", "not_found")

        def _run_clone():
            updated = clone_repository(repo)
            return _repo_summary(updated, include_public_key=True)

        return run_service(_run_clone)

    name = require_str(params, "name", max_len=64)
    remote_url = require_str(params, "remote_url", max_len=500)
    if not name or not remote_url:
        return err("name + remote_url requis (ou repo_id)")

    def _run_create():
        repo = create_repository(
            owner=user,
            name=name,
            remote_url=remote_url,
            branch=require_str(params, "branch", default="main") or "main",
            relative_path=require_str(params, "relative_path", max_len=500),
            deploy_script=require_str(params, "deploy_script", max_len=200),
            auto_deploy=bool(params["auto_deploy"]) if "auto_deploy" in params else True,
            label=require_str(params, "label", max_len=120),
            notes=require_str(params, "notes", max_len=200),
            clone_now=bool(params["clone_now"]) if "clone_now" in params else True,
        )
        return _repo_summary(repo, include_public_key=True)

    return run_service(_run_create)


@register_tool(
    name="run_git_deploy_script",
    description="Exécute le script de déploiement d'un dépôt Git (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"repo_id": {"type": "integer"}},
        "required": ["repo_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def run_git_deploy_script(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.git_deploy.services import repos_qs, run_deploy_script

    repo = repos_qs(user).filter(pk=require_int(params, "repo_id")).first()
    if not repo:
        return err("Dépôt Git introuvable", "not_found")

    def _run():
        updated = run_deploy_script(repo)
        return _repo_summary(updated)

    return run_service(_run)


@register_tool(
    name="generate_git_deploy_key",
    description=(
        "Régénère la clé de déploiement d'un dépôt Git (confirmation requise). "
        "Ne renvoie que la clé publique."
    ),
    parameters={
        "type": "object",
        "properties": {"repo_id": {"type": "integer"}},
        "required": ["repo_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def generate_git_deploy_key(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.git_deploy.services import generate_deploy_key, repos_qs

    repo = repos_qs(user).filter(pk=require_int(params, "repo_id")).first()
    if not repo:
        return err("Dépôt Git introuvable", "not_found")

    def _run():
        updated = generate_deploy_key(repo)
        return {
            "id": updated.pk,
            "name": updated.name,
            "deploy_key_public": updated.deploy_key_public or "",
            "private_key_returned": False,
        }

    return run_service(_run)


@register_tool(
    name="delete_git_repository",
    description="Supprime un dépôt Git (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "repo_id": {"type": "integer"},
            "remove_files": {"type": "boolean"},
        },
        "required": ["repo_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_git_repository(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.git_deploy.services import delete_repository, repos_qs

    repo = repos_qs(user).filter(pk=require_int(params, "repo_id")).first()
    if not repo:
        return err("Dépôt Git introuvable", "not_found")
    name = repo.name

    def _run():
        delete_repository(repo, remove_files=bool(params.get("remove_files", False)))
        return {"deleted": name}

    return run_service(_run)
