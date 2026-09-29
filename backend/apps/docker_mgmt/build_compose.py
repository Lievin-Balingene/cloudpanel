"""Build d'images, liste images, Docker Compose — panel Docker complet."""
from __future__ import annotations

import json
import logging
import re
import secrets
import subprocess
from collections.abc import Callable
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException
from apps.docker_mgmt.models import DockerBuildJob, DockerComposeProject
from apps.docker_mgmt.services import (
    NAME_RE,
    _assert_docker_quota,
    _run_docker,
    config_root,
    docker_binary,
    open_docker_host_ports,
    provision_mode,
    resolve_ports,
)
from apps.files.services import resolve_path

logger = logging.getLogger(__name__)

COMPOSE_FILES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
IMAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,118}$", re.I)


def user_image_prefix(owner: User) -> str:
    safe = re.sub(r"[^a-z0-9_-]", "-", owner.username.lower())
    return f"vz_{safe}"


def scoped_image_name(owner: User, name: str) -> str:
    name = name.strip().lower().replace(" ", "-")
    if not IMAGE_NAME_RE.match(name):
        raise VZoneAPIException(detail="Nom d'image invalide.", code="invalid_image_name", status_code=400)
    prefix = user_image_prefix(owner)
    if name.startswith(f"{prefix}_"):
        return name
    return f"{prefix}_{name}"


def full_image_ref(owner: User, image_name: str, tag: str = "latest") -> str:
    scoped = scoped_image_name(owner, image_name)
    tag = (tag or "latest").strip() or "latest"
    return f"{scoped}:{tag}"


def builds_qs(user: User):
    qs = DockerBuildJob.objects.select_related("owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        from django.db.models import Q

        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def compose_qs(user: User):
    qs = DockerComposeProject.objects.select_related("owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        from django.db.models import Q

        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def _resolve_compose_paths(owner: User, project_path: str, compose_file: str) -> tuple[Path, Path]:
    project_dir = resolve_path(owner, project_path)
    if not project_dir.is_dir():
        raise VZoneAPIException(
            detail="Dossier projet introuvable.",
            code="project_not_found",
            status_code=404,
        )
    compose_path = resolve_path(owner, f"{project_path.rstrip('/')}/{compose_file}")
    if not compose_path.is_file():
        raise VZoneAPIException(
            detail=f"Fichier compose introuvable: {compose_file}",
            code="compose_not_found",
            status_code=404,
        )
    return project_dir, compose_path


def _resolve_build_paths(owner: User, context_path: str, dockerfile: str) -> tuple[Path, Path]:
    context = resolve_path(owner, context_path)
    if not context.is_dir():
        raise VZoneAPIException(
            detail="Contexte de build introuvable.",
            code="context_not_found",
            status_code=404,
        )
    df_rel = f"{context_path.rstrip('/')}/{dockerfile}".lstrip("/")
    dockerfile_path = resolve_path(owner, df_rel)
    if not dockerfile_path.is_file():
        raise VZoneAPIException(
            detail=f"Dockerfile introuvable: {dockerfile}",
            code="dockerfile_not_found",
            status_code=404,
        )
    return context, dockerfile_path


def _compose_project_name(owner: User, name: str) -> str:
    safe = re.sub(r"[^a-z0-9_-]", "-", owner.username.lower())
    return f"vz_{safe}_{name}"


def _run_docker_stream(
    args: list[str],
    *,
    on_line: Callable[[str], None],
    timeout: int = 1800,
    cwd: Path | None = None,
) -> int:
    cmd = [docker_binary(), *args]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            on_line(line.rstrip("\n"))
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        raise VZoneAPIException(
            detail="Commande Docker expirée (timeout).",
            code="docker_timeout",
            status_code=504,
        ) from exc


@transaction.atomic
def create_build_job(
    *,
    owner: User,
    name: str,
    context_path: str,
    dockerfile: str = "Dockerfile",
    image_name: str = "",
    tag: str = "latest",
    no_cache: bool = False,
    async_run: bool = True,
) -> DockerBuildJob:
    _assert_docker_quota(owner)
    slug = name.strip().lower().replace(" ", "-")
    if not NAME_RE.match(slug):
        raise VZoneAPIException(detail="Nom de build invalide.", code="invalid_name", status_code=400)
    if DockerBuildJob.objects.filter(owner=owner, name=slug).exists():
        raise VZoneAPIException(detail="Ce build existe déjà.", code="exists", status_code=400)

    img_name = image_name.strip() or slug
    _resolve_build_paths(owner, context_path, dockerfile or "Dockerfile")

    job = DockerBuildJob.objects.create(
        owner=owner,
        name=slug,
        context_path=context_path.strip().strip("/"),
        dockerfile=(dockerfile or "Dockerfile").strip(),
        image_name=img_name,
        tag=(tag or "latest").strip() or "latest",
        no_cache=bool(no_cache),
        status=DockerBuildJob.Status.PENDING,
    )
    job_id = job.pk
    if (not async_run) or provision_mode() == "mock":
        return run_build_job(job_id)
    transaction.on_commit(lambda: _dispatch_build_task(job_id))
    return job


def _dispatch_build_task(job_id: int) -> None:
    try:
        from apps.docker_mgmt.tasks import execute_docker_build

        async_result = execute_docker_build.delay(job_id)
        DockerBuildJob.objects.filter(pk=job_id).update(celery_task_id=async_result.id or "")
    except Exception:  # noqa: BLE001
        logger.exception("Celery build dispatch failed — run inline")
        run_build_job(job_id)


def run_build_job(job_id: int) -> DockerBuildJob:
    job = DockerBuildJob.objects.select_related("owner").get(pk=job_id)
    if job.status == DockerBuildJob.Status.COMPLETED:
        return job

    image_ref = full_image_ref(job.owner, job.image_name, job.tag)
    job.status = DockerBuildJob.Status.RUNNING
    job.started_at = timezone.now()
    job.progress = 5
    job.last_error = ""
    job.append_log(f"Build {image_ref}")
    job.save(update_fields=["status", "started_at", "progress", "log", "last_error", "updated_at"])

    try:
        if provision_mode() == "mock":
            job.append_log("mock: docker build …")
            job.built_image_ref = image_ref
            job.progress = 100
            job.status = DockerBuildJob.Status.COMPLETED
            job.completed_at = timezone.now()
            job.save()
            return job

        context, dockerfile_path = _resolve_build_paths(job.owner, job.context_path, job.dockerfile)
        args = [
            "build",
            "-t",
            image_ref,
            "-f",
            str(dockerfile_path),
        ]
        if job.no_cache:
            args.append("--no-cache")
        args.append(str(context))

        line_count = 0

        def on_line(line: str) -> None:
            nonlocal line_count
            line_count += 1
            job.append_log(line)
            job.progress = min(95, 5 + line_count // 2)
            job.save(update_fields=["log", "progress", "updated_at"])

        rc = _run_docker_stream(args, on_line=on_line, timeout=1800)
        if rc != 0:
            raise VZoneAPIException(
                detail=f"docker build a échoué (code {rc}).",
                code="build_failed",
                status_code=502,
            )
        job.built_image_ref = image_ref
        job.progress = 100
        job.status = DockerBuildJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save()
    except VZoneAPIException as exc:
        job.status = DockerBuildJob.Status.FAILED
        job.last_error = str(exc.detail)
        job.append_log(f"ERREUR: {exc.detail}")
        job.completed_at = timezone.now()
        job.save()
        raise
    except Exception as exc:  # noqa: BLE001
        job.status = DockerBuildJob.Status.FAILED
        job.last_error = str(exc)
        job.append_log(f"ERREUR: {exc}")
        job.completed_at = timezone.now()
        job.save()
        raise VZoneAPIException(
            detail=str(exc),
            code="build_failed",
            status_code=502,
        ) from exc
    return job


def list_local_images(owner: User) -> list[dict]:
    if provision_mode() == "mock":
        prefix = user_image_prefix(owner)
        return [
            {
                "repository": f"{prefix}_demo",
                "tag": "latest",
                "id": secrets.token_hex(6),
                "size": "42MB",
                "created": "mock",
                "owned": True,
            }
        ]
    prefix = user_image_prefix(owner)
    result = _run_docker(["images", "--format", "{{json .}}"], timeout=60)
    images: list[dict] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        repo = row.get("Repository") or ""
        if owner.role != User.Role.ADMINISTRATOR and not repo.startswith(prefix):
            continue
        images.append(
            {
                "repository": repo,
                "tag": row.get("Tag") or "",
                "id": (row.get("ID") or "")[:12],
                "size": row.get("Size") or "",
                "created": row.get("CreatedSince") or row.get("CreatedAt") or "",
                "owned": repo.startswith(prefix),
            }
        )
    return images


def pull_image(owner: User, image: str, tag: str = "latest") -> dict:
    image = image.strip()
    tag = (tag or "latest").strip() or "latest"
    ref = f"{image}:{tag}" if ":" not in image else image
    if provision_mode() == "mock":
        return {"image_ref": ref, "status": "pulled"}
    _run_docker(["pull", ref], timeout=600)
    return {"image_ref": ref, "status": "pulled"}


def remove_local_image(owner: User, repository: str, tag: str = "latest") -> None:
    repository = repository.strip()
    tag = (tag or "latest").strip() or "latest"
    prefix = user_image_prefix(owner)
    if owner.role != User.Role.ADMINISTRATOR and not repository.startswith(prefix):
        raise VZoneAPIException(
            detail="Suppression réservée à vos images (préfixe vz_).",
            code="image_forbidden",
            status_code=403,
        )
    ref = f"{repository}:{tag}"
    if provision_mode() == "mock":
        return
    _run_docker(["rmi", "-f", ref], timeout=120)


@transaction.atomic
def create_compose_project(
    *,
    owner: User,
    name: str,
    project_path: str,
    compose_file: str = "",
) -> DockerComposeProject:
    _assert_docker_quota(owner)
    slug = name.strip().lower().replace(" ", "-")
    if not NAME_RE.match(slug):
        raise VZoneAPIException(detail="Nom de projet invalide.", code="invalid_name", status_code=400)
    if DockerComposeProject.objects.filter(owner=owner, name=slug).exists():
        raise VZoneAPIException(detail="Ce projet compose existe déjà.", code="exists", status_code=400)

    project_path = project_path.strip().strip("/")
    cf = compose_file.strip() if compose_file else ""
    if not cf:
        project_dir = resolve_path(owner, project_path)
        for candidate in COMPOSE_FILES:
            if (project_dir / candidate).is_file():
                cf = candidate
                break
        if not cf:
            raise VZoneAPIException(
                detail="Aucun docker-compose.yml trouvé dans le dossier.",
                code="compose_not_found",
                status_code=404,
            )
    _resolve_compose_paths(owner, project_path, cf)

    return DockerComposeProject.objects.create(
        owner=owner,
        name=slug,
        project_path=project_path,
        compose_file=cf,
        status=DockerComposeProject.Status.CREATED,
    )


def _dispatch_compose_task(project_id: int, action: str) -> None:
    try:
        from apps.docker_mgmt.tasks import execute_docker_compose

        async_result = execute_docker_compose.delay(project_id, action)
        DockerComposeProject.objects.filter(pk=project_id).update(celery_task_id=async_result.id or "")
    except Exception:  # noqa: BLE001
        logger.exception("Celery compose dispatch failed — run inline")
        run_compose_action(project_id, action)


def compose_up(project: DockerComposeProject, *, build: bool = True, async_run: bool = True) -> DockerComposeProject:
    project_id = project.pk
    if (not async_run) or provision_mode() == "mock":
        return run_compose_action(project_id, "up", build=build)
    transaction.on_commit(lambda: _dispatch_compose_task(project_id, "up"))
    project.status = DockerComposeProject.Status.RUNNING
    project.save(update_fields=["status", "updated_at"])
    return project


def compose_down(project: DockerComposeProject, *, async_run: bool = True) -> DockerComposeProject:
    project_id = project.pk
    if (not async_run) or provision_mode() == "mock":
        return run_compose_action(project_id, "down")
    transaction.on_commit(lambda: _dispatch_compose_task(project_id, "down"))
    return project


def run_compose_action(project_id: int, action: str, *, build: bool = True) -> DockerComposeProject:
    project = DockerComposeProject.objects.select_related("owner").get(pk=project_id)
    project_dir, compose_path = _resolve_compose_paths(
        project.owner, project.project_path, project.compose_file
    )
    project_name = _compose_project_name(project.owner, project.name)

    try:
        if provision_mode() == "mock":
            project.append_log(f"mock: docker compose {action}")
            project.status = (
                DockerComposeProject.Status.RUNNING
                if action == "up"
                else DockerComposeProject.Status.STOPPED
            )
            project.last_error = ""
            if action == "up":
                project.last_deployed_at = timezone.now()
            project.save()
            return project

        if action == "up":
            args = [
                "compose",
                "-f",
                str(compose_path),
                "-p",
                project_name,
                "up",
                "-d",
            ]
            if build:
                args.append("--build")
            project.append_log(f"docker compose up -d --build ({project_name})")
        elif action == "down":
            args = ["compose", "-f", str(compose_path), "-p", project_name, "down", "--remove-orphans"]
            project.append_log(f"docker compose down ({project_name})")
        else:
            raise VZoneAPIException(detail="Action compose invalide.", code="invalid_action", status_code=400)

        def on_line(line: str) -> None:
            project.append_log(line)
            project.save(update_fields=["log", "updated_at"])

        rc = _run_docker_stream(args, on_line=on_line, timeout=1800, cwd=project_dir)
        if rc != 0:
            raise VZoneAPIException(
                detail=f"docker compose {action} a échoué (code {rc}).",
                code="compose_failed",
                status_code=502,
            )

        if action == "up":
            _open_compose_ports(project)
            project.status = DockerComposeProject.Status.RUNNING
            project.last_deployed_at = timezone.now()
        else:
            project.status = DockerComposeProject.Status.STOPPED
        project.last_error = ""
        project.save()
    except VZoneAPIException as exc:
        project.status = DockerComposeProject.Status.ERROR
        project.last_error = str(exc.detail)
        project.append_log(f"ERREUR: {exc.detail}")
        project.save()
        raise
    except Exception as exc:  # noqa: BLE001
        project.status = DockerComposeProject.Status.ERROR
        project.last_error = str(exc)
        project.append_log(f"ERREUR: {exc}")
        project.save()
        raise VZoneAPIException(detail=str(exc), code="compose_failed", status_code=502) from exc
    return project


def _open_compose_ports(project: DockerComposeProject) -> None:
    """Ouvre les ports publiés détectés via docker compose ps."""
    if provision_mode() == "mock":
        return
    project_dir, compose_path = _resolve_compose_paths(
        project.owner, project.project_path, project.compose_file
    )
    project_name = _compose_project_name(project.owner, project.name)
    try:
        result = _run_docker(
            ["compose", "-f", str(compose_path), "-p", project_name, "ps", "--format", "json"],
            timeout=60,
        )
        ports: dict[str, str] = {}
        for line in (result.stdout or "").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            pub = row.get("Publishers") or row.get("Ports") or ""
            if isinstance(pub, list):
                for p in pub:
                    hp = p.get("PublishedPort") or p.get("HostPort")
                    if hp:
                        ports[str(hp)] = "80"
            elif isinstance(pub, str) and "->" in pub:
                for part in pub.split(","):
                    if "->" in part:
                        host = part.split("->")[0].split(":")[-1]
                        ports[host.strip()] = "80"
        if ports:
            open_docker_host_ports(ports)
    except Exception:  # noqa: BLE001
        logger.warning("Impossible d'ouvrir les ports compose pour %s", project.name)


def remove_compose_project(project: DockerComposeProject) -> None:
    if project.status == DockerComposeProject.Status.RUNNING:
        try:
            run_compose_action(project.pk, "down")
        except VZoneAPIException:
            pass
    project.delete()


def write_dockerfile_template(owner: User, context_path: str, *, kind: str = "node") -> Path:
    """Crée un Dockerfile minimal dans le home utilisateur."""
    context = resolve_path(owner, context_path)
    context.mkdir(parents=True, exist_ok=True)
    dockerfile = context / "Dockerfile"
    if dockerfile.exists():
        raise VZoneAPIException(detail="Dockerfile déjà présent.", code="exists", status_code=400)

    if kind == "nginx":
        content = """FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE 80
"""
    elif kind == "python":
        content = """FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "main.py"]
"""
    else:
        content = """FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE 3000
CMD ["node", "server.js"]
"""
    dockerfile.write_text(content, encoding="utf-8")
    return dockerfile


def overview_build_compose(user: User) -> dict:
    builds = builds_qs(user)
    compose = compose_qs(user)
    return {
        "builds": builds.count(),
        "builds_running": builds.filter(status=DockerBuildJob.Status.RUNNING).count(),
        "compose_projects": compose.count(),
        "compose_running": compose.filter(status=DockerComposeProject.Status.RUNNING).count(),
        "images": len(list_local_images(user)),
        "image_prefix": user_image_prefix(user),
    }
