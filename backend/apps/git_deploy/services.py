"""Services Git deploy : clone, pull, webhook, clés SSH, logs."""
from __future__ import annotations

import logging
import re
import secrets
import shutil
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.files.services import user_home
from apps.git_deploy.models import GitDeployLog, GitRepository

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
MAX_REPOS_DEFAULT = 20


def repos_qs(user: User) -> QuerySet[GitRepository]:
    qs = GitRepository.objects.select_related("owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def logs_qs(user: User) -> QuerySet[GitDeployLog]:
    qs = GitDeployLog.objects.select_related("repository", "repository__owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(
            Q(repository__owner=user) | Q(repository__owner__parent=user)
        )
    return qs.filter(repository__owner=user)


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_GIT_PROVISION_MODE", "auto").lower()
    return mode if mode in {"auto", "live", "mock"} else "auto"


def config_root() -> Path:
    root = Path(getattr(settings, "VZONE_GIT_CONFIG_DIR", None) or (Path(settings.VZONE_DATA_ROOT) / "git"))
    root.mkdir(parents=True, exist_ok=True)
    (root / "keys").mkdir(exist_ok=True)
    return root


def _assert_git_allowed(owner: User) -> None:
    try:
        assignment = owner.package_assignment
    except Exception:  # RelatedObjectDoesNotExist
        assignment = None
    if assignment and assignment.package and not assignment.package.allow_git:
        raise VZoneAPIException(
            detail="Git n'est pas autorisé sur ce package.",
            code="git_disabled",
            status_code=403,
        )
    limit = int(getattr(settings, "VZONE_GIT_MAX_REPOS", MAX_REPOS_DEFAULT))
    if owner.role == User.Role.ADMINISTRATOR and limit == 0:
        return
    used = GitRepository.objects.filter(owner=owner).count()
    if limit > 0 and used >= limit:
        raise QuotaExceeded(
            detail="Quota de dépôts Git atteint.",
            extra={"limit": limit, "used": used},
        )


def resolve_repo_path(owner: User, relative_path: str) -> tuple[str, Path]:
    rel = (relative_path or "").replace("\\", "/").strip("/")
    if not rel or ".." in Path(rel).parts:
        raise VZoneAPIException(detail="Chemin Git invalide.", code="invalid_path", status_code=400)
    home = user_home(owner)
    target = (home / rel).resolve()
    try:
        target.relative_to(home)
    except ValueError as exc:
        raise VZoneAPIException(
            detail="Chemin hors du home autorisé.",
            code="path_forbidden",
            status_code=403,
        ) from exc
    return rel, target


def git_binary() -> str:
    configured = getattr(settings, "VZONE_GIT_BIN", "") or ""
    if configured:
        return configured
    return shutil.which("git") or "git"


def _run_git(args: list[str], *, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = [git_binary(), *args]
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            env=env,
            timeout=300,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        stderr = getattr(exc, "stderr", None) or str(exc)
        raise VZoneAPIException(
            detail="Échec commande Git.",
            code="git_cmd_failed",
            status_code=502,
            extra={"stderr": stderr, "cmd": cmd},
        ) from exc


def _add_log(
    repo: GitRepository,
    event_type: str,
    *,
    success: bool = True,
    message: str = "",
    commit_hash: str = "",
) -> GitDeployLog:
    return GitDeployLog.objects.create(
        repository=repo,
        event_type=event_type,
        success=success,
        message=message[:4000],
        commit_hash=commit_hash,
    )


def generate_deploy_key(repo: GitRepository) -> GitRepository:
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_ssh = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )
        .decode("utf-8")
    )
    public_ssh = f"{public_ssh} vzone-{repo.owner.username}-{repo.name}"
    repo.deploy_key_private = private_pem
    repo.deploy_key_public = public_ssh
    repo.save(update_fields=["deploy_key_private", "deploy_key_public", "updated_at"])

    key_dir = config_root() / "keys" / str(repo.owner_id)
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / f"{repo.name}").write_text(private_pem, encoding="utf-8")
    (key_dir / f"{repo.name}.pub").write_text(public_ssh + "\n", encoding="utf-8")
    _add_log(repo, GitDeployLog.Event.KEYGEN, message="Clé deploy générée")
    return repo


def _ssh_env(repo: GitRepository) -> dict | None:
    if not repo.deploy_key_private:
        return None
    import os

    key_path = config_root() / "keys" / str(repo.owner_id) / repo.name
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(repo.deploy_key_private, encoding="utf-8")
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = f'ssh -i "{key_path}" -o StrictHostKeyChecking=accept-new'
    return env


def _read_head(repo_path: Path) -> tuple[str, str]:
    head_file = repo_path / ".git" / "HEAD"
    if not (repo_path / ".git").exists():
        return "", ""
    try:
        if provision_mode() == "mock":
            ref = (repo_path / ".git" / "COMMIT").read_text(encoding="utf-8").strip() if (repo_path / ".git" / "COMMIT").exists() else "mockcommit"
            msg = (repo_path / ".git" / "MESSAGE").read_text(encoding="utf-8").strip() if (repo_path / ".git" / "MESSAGE").exists() else "mock commit"
            return ref[:40], msg[:255]
        result = _run_git(["rev-parse", "HEAD"], cwd=repo_path)
        commit = result.stdout.strip()
        msg = _run_git(["log", "-1", "--pretty=%s"], cwd=repo_path).stdout.strip()
        return commit, msg[:255]
    except Exception:  # noqa: BLE001
        return "", ""


@transaction.atomic
def create_repository(
    *,
    owner: User,
    name: str,
    remote_url: str,
    branch: str = "main",
    relative_path: str = "",
    deploy_script: str = "",
    auto_deploy: bool = True,
    label: str = "",
    notes: str = "",
    clone_now: bool = True,
) -> GitRepository:
    _assert_git_allowed(owner)
    slug = name.strip().lower().replace(" ", "-")
    if not NAME_RE.match(slug):
        raise VZoneAPIException(detail="Nom de dépôt invalide.", code="invalid_name", status_code=400)
    url = remote_url.strip()
    if not url or not (url.startswith("http://") or url.startswith("https://") or url.startswith("git@")):
        raise VZoneAPIException(detail="URL Git invalide.", code="invalid_url", status_code=400)
    if GitRepository.objects.filter(owner=owner, name=slug).exists():
        raise VZoneAPIException(detail="Ce dépôt existe déjà.", code="exists", status_code=400)

    rel = relative_path.strip() or f"repositories/{slug}"
    rel, repo_path = resolve_repo_path(owner, rel)
    if repo_path.exists() and any(repo_path.iterdir()):
        raise VZoneAPIException(
            detail="Le chemin cible n'est pas vide.",
            code="path_not_empty",
            status_code=400,
        )

    repo = GitRepository.objects.create(
        owner=owner,
        name=slug,
        label=label or slug,
        remote_url=url,
        branch=(branch or "main").strip() or "main",
        relative_path=rel,
        deploy_script=deploy_script.strip(),
        auto_deploy=auto_deploy,
        webhook_token=GitRepository.generate_webhook_token(),
        notes=notes,
        status=GitRepository.Status.IDLE,
    )
    generate_deploy_key(repo)
    if clone_now:
        clone_repository(repo)
    return repo


def clone_repository(repo: GitRepository) -> GitRepository:
    _, repo_path = resolve_repo_path(repo.owner, repo.relative_path)
    repo.status = GitRepository.Status.CLONING
    repo.last_error = ""
    repo.save(update_fields=["status", "last_error", "updated_at"])

    try:
        if provision_mode() == "mock":
            repo_path.mkdir(parents=True, exist_ok=True)
            git_dir = repo_path / ".git"
            git_dir.mkdir(exist_ok=True)
            commit = secrets.token_hex(20)
            (git_dir / "COMMIT").write_text(commit, encoding="utf-8")
            (git_dir / "MESSAGE").write_text("Initial mock clone", encoding="utf-8")
            (repo_path / "README.md").write_text(f"# {repo.name}\n", encoding="utf-8")
            message = f"mock clone {repo.remote_url}@{repo.branch}"
        else:
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            env = _ssh_env(repo)
            _run_git(
                ["clone", "--branch", repo.branch, "--single-branch", repo.remote_url, str(repo_path)],
                env=env,
            )
            message = f"cloned {repo.remote_url}@{repo.branch}"

        commit, msg = _read_head(repo_path)
        repo.last_commit = commit
        repo.last_commit_message = msg
        repo.status = GitRepository.Status.READY
        repo.last_deploy_at = timezone.now()
        repo.save()
        _add_log(repo, GitDeployLog.Event.CLONE, message=message, commit_hash=commit)
    except VZoneAPIException as exc:
        repo.status = GitRepository.Status.ERROR
        repo.last_error = str(exc.detail)
        repo.save(update_fields=["status", "last_error", "updated_at"])
        _add_log(repo, GitDeployLog.Event.CLONE, success=False, message=str(exc.detail))
        raise
    return repo


def pull_repository(repo: GitRepository) -> GitRepository:
    _, repo_path = resolve_repo_path(repo.owner, repo.relative_path)
    if not (repo_path / ".git").exists():
        return clone_repository(repo)

    repo.status = GitRepository.Status.DEPLOYING
    repo.last_error = ""
    repo.save(update_fields=["status", "last_error", "updated_at"])

    try:
        if provision_mode() == "mock":
            commit = secrets.token_hex(20)
            (repo_path / ".git" / "COMMIT").write_text(commit, encoding="utf-8")
            (repo_path / ".git" / "MESSAGE").write_text("Mock pull update", encoding="utf-8")
            message = f"mock pull origin/{repo.branch}"
        else:
            env = _ssh_env(repo)
            _run_git(["fetch", "origin", repo.branch], cwd=repo_path, env=env)
            _run_git(["checkout", repo.branch], cwd=repo_path, env=env)
            _run_git(["pull", "origin", repo.branch], cwd=repo_path, env=env)
            message = f"pulled origin/{repo.branch}"
            commit, _ = _read_head(repo_path)

        commit, msg = _read_head(repo_path)
        repo.last_commit = commit
        repo.last_commit_message = msg
        repo.status = GitRepository.Status.READY
        repo.last_deploy_at = timezone.now()
        repo.save()
        _add_log(repo, GitDeployLog.Event.PULL, message=message, commit_hash=commit)

        if repo.deploy_script:
            run_deploy_script(repo)
    except VZoneAPIException as exc:
        repo.status = GitRepository.Status.ERROR
        repo.last_error = str(exc.detail)
        repo.save(update_fields=["status", "last_error", "updated_at"])
        _add_log(repo, GitDeployLog.Event.PULL, success=False, message=str(exc.detail))
        raise
    return repo


def run_deploy_script(repo: GitRepository) -> GitRepository:
    if not repo.deploy_script:
        return repo
    _, repo_path = resolve_repo_path(repo.owner, repo.relative_path)
    script = (repo_path / repo.deploy_script).resolve()
    try:
        script.relative_to(repo_path)
    except ValueError as exc:
        raise VZoneAPIException(detail="Script hors du dépôt.", code="invalid_script", status_code=400) from exc

    if provision_mode() == "mock":
        log_path = repo_path / "logs"
        log_path.mkdir(exist_ok=True)
        (log_path / "deploy.log").write_text(f"mock ran {repo.deploy_script}\n", encoding="utf-8")
        _add_log(repo, GitDeployLog.Event.DEPLOY, message=f"mock {repo.deploy_script}", commit_hash=repo.last_commit)
        return repo

    if not script.exists():
        raise VZoneAPIException(detail="Script de déploiement introuvable.", code="no_script", status_code=400)
    try:
        result = subprocess.run(
            ["bash", str(script)] if script.suffix in {".sh", ""} else [str(script)],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=600,
        )
        _add_log(
            repo,
            GitDeployLog.Event.DEPLOY,
            message=(result.stdout or result.stderr or "ok")[:4000],
            commit_hash=repo.last_commit,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        stderr = getattr(exc, "stderr", None) or str(exc)
        _add_log(repo, GitDeployLog.Event.DEPLOY, success=False, message=stderr[:4000])
        raise VZoneAPIException(
            detail="Échec script de déploiement.",
            code="deploy_failed",
            status_code=502,
            extra={"stderr": stderr},
        ) from exc
    return repo


def webhook_deploy(repo: GitRepository, *, token: str) -> GitRepository:
    if not secrets.compare_digest(repo.webhook_token, token):
        raise VZoneAPIException(detail="Token webhook invalide.", code="invalid_token", status_code=403)
    if not repo.is_active or not repo.auto_deploy:
        raise VZoneAPIException(detail="Auto-deploy désactivé.", code="auto_deploy_off", status_code=400)
    _add_log(repo, GitDeployLog.Event.WEBHOOK, message="Webhook reçu")
    return pull_repository(repo)


@transaction.atomic
def update_repository(
    repo: GitRepository,
    *,
    label: str | None = None,
    branch: str | None = None,
    deploy_script: str | None = None,
    auto_deploy: bool | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
) -> GitRepository:
    if label is not None:
        repo.label = label
    if branch is not None:
        repo.branch = branch.strip() or repo.branch
    if deploy_script is not None:
        repo.deploy_script = deploy_script.strip()
    if auto_deploy is not None:
        repo.auto_deploy = auto_deploy
    if notes is not None:
        repo.notes = notes
    if is_active is not None:
        repo.is_active = is_active
    repo.save()
    return repo


@transaction.atomic
def delete_repository(repo: GitRepository, *, remove_files: bool = False) -> None:
    key_dir = config_root() / "keys" / str(repo.owner_id)
    for suffix in ("", ".pub"):
        path = key_dir / f"{repo.name}{suffix}"
        if path.exists():
            path.unlink(missing_ok=True)
    if remove_files:
        try:
            _, repo_path = resolve_repo_path(repo.owner, repo.relative_path)
            shutil.rmtree(repo_path, ignore_errors=True)
        except VZoneAPIException:
            pass
    repo.delete()


def rotate_webhook_token(repo: GitRepository) -> GitRepository:
    repo.webhook_token = GitRepository.generate_webhook_token()
    repo.save(update_fields=["webhook_token", "updated_at"])
    return repo


def overview_for(user: User) -> dict:
    qs = repos_qs(user)
    return {
        "repositories": qs.count(),
        "ready": qs.filter(status=GitRepository.Status.READY).count(),
        "error": qs.filter(status=GitRepository.Status.ERROR).count(),
        "auto_deploy": qs.filter(auto_deploy=True).count(),
        "provision_mode": provision_mode(),
    }
