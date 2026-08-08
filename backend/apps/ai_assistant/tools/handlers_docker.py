"""Tools Docker (conteneurs)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


def _container_summary(c) -> dict[str, Any]:
    return {
        "id": c.pk,
        "name": c.name,
        "label": c.label or "",
        "image": getattr(c, "image_ref", None) or f"{c.image}:{c.tag}",
        "status": c.status,
        "ports": c.ports or {},
        "memory_mb": c.memory_mb,
        "cpus": str(c.cpus),
        "is_active": c.is_active,
        "container_id": (c.container_id or "")[:12],
    }


@register_tool(
    name="list_docker_containers",
    description="Liste les conteneurs Docker du compte.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_docker_containers(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.docker_mgmt.models import DockerContainer
    from apps.docker_mgmt.services import containers_qs, overview_for

    containers = [
        _container_summary(c)
        for c in containers_qs(user).exclude(status=DockerContainer.Status.REMOVED)[:80]
    ]
    return ok(overview=overview_for(user), containers=containers)


@register_tool(
    name="get_docker_logs",
    description="Lit les logs d'un conteneur Docker (tail).",
    parameters={
        "type": "object",
        "properties": {
            "container_id": {"type": "integer"},
            "tail": {"type": "integer"},
        },
        "required": ["container_id"],
        "additionalProperties": False,
    },
)
def get_docker_logs(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.docker_mgmt.services import containers_qs, read_container_logs

    container = containers_qs(user).filter(pk=require_int(params, "container_id")).first()
    if not container:
        return err("Conteneur introuvable", "not_found")
    tail = require_int(params, "tail") or 100

    def _run():
        logs = read_container_logs(container, tail=tail)
        text = str(logs or "")
        return {
            "id": container.pk,
            "name": container.name,
            "tail": tail,
            "logs": text[:8000],
            "truncated": len(text) > 8000,
        }

    return run_service(_run)


@register_tool(
    name="create_docker_container",
    description="Crée un conteneur Docker (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "image": {"type": "string"},
            "tag": {"type": "string"},
            "ports": {"type": "object"},
            "env_vars": {"type": "object"},
            "volumes": {"type": "array", "items": {"type": "string"}},
            "command": {"type": "string"},
            "restart_policy": {"type": "string"},
            "memory_mb": {"type": "integer"},
            "cpus": {"type": "number"},
            "label": {"type": "string"},
            "notes": {"type": "string"},
            "start_now": {"type": "boolean"},
        },
        "required": ["name", "image"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_docker_container(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.docker_mgmt.models import DockerContainer
    from apps.docker_mgmt.services import create_container

    name = require_str(params, "name", max_len=64)
    image = require_str(params, "image", max_len=200)
    if not name or not image:
        return err("name + image requis")

    ports = params.get("ports") if isinstance(params.get("ports"), dict) else None
    env_vars = params.get("env_vars") if isinstance(params.get("env_vars"), dict) else None
    volumes = params.get("volumes") if isinstance(params.get("volumes"), list) else None
    cpus = params.get("cpus", 1)

    def _run():
        container = create_container(
            owner=user,
            name=name,
            image=image,
            tag=require_str(params, "tag", default="latest") or "latest",
            ports=ports,
            env_vars=env_vars,
            volumes=volumes,
            command=require_str(params, "command", max_len=500),
            restart_policy=require_str(
                params, "restart_policy", default=DockerContainer.RestartPolicy.UNLESS_STOPPED
            )
            or DockerContainer.RestartPolicy.UNLESS_STOPPED,
            memory_mb=require_int(params, "memory_mb") or 512,
            cpus=Decimal(str(cpus)),
            label=require_str(params, "label", max_len=120),
            notes=require_str(params, "notes", max_len=200),
            start_now=bool(params["start_now"]) if "start_now" in params else True,
        )
        return _container_summary(container)

    return run_service(_run)


@register_tool(
    name="start_docker_container",
    description="Démarre un conteneur Docker (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"container_id": {"type": "integer"}},
        "required": ["container_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def start_docker_container(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.docker_mgmt.services import containers_qs, start_container

    container = containers_qs(user).filter(pk=require_int(params, "container_id")).first()
    if not container:
        return err("Conteneur introuvable", "not_found")

    def _run():
        return _container_summary(start_container(container))

    return run_service(_run)


@register_tool(
    name="stop_docker_container",
    description="Arrête un conteneur Docker (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"container_id": {"type": "integer"}},
        "required": ["container_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def stop_docker_container(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.docker_mgmt.services import containers_qs, stop_container

    container = containers_qs(user).filter(pk=require_int(params, "container_id")).first()
    if not container:
        return err("Conteneur introuvable", "not_found")

    def _run():
        return _container_summary(stop_container(container))

    return run_service(_run)


@register_tool(
    name="restart_docker_container",
    description="Redémarre un conteneur Docker (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"container_id": {"type": "integer"}},
        "required": ["container_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def restart_docker_container(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.docker_mgmt.services import containers_qs, restart_container

    container = containers_qs(user).filter(pk=require_int(params, "container_id")).first()
    if not container:
        return err("Conteneur introuvable", "not_found")

    def _run():
        return _container_summary(restart_container(container))

    return run_service(_run)


@register_tool(
    name="remove_docker_container",
    description="Supprime un conteneur Docker (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "container_id": {"type": "integer"},
            "force": {"type": "boolean"},
        },
        "required": ["container_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def remove_docker_container(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.docker_mgmt.services import containers_qs, remove_container

    container = containers_qs(user).filter(pk=require_int(params, "container_id")).first()
    if not container:
        return err("Conteneur introuvable", "not_found")
    name = container.name

    def _run():
        remove_container(container, force=bool(params.get("force", True)))
        return {"deleted": name}

    return run_service(_run)
