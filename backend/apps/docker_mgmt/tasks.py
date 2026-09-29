"""Tâches Celery — build Docker et Compose async."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="docker_mgmt.execute_docker_build", bind=True, max_retries=0)
def execute_docker_build(self, job_id: int) -> dict:
    from apps.docker_mgmt.build_compose import run_build_job

    try:
        job = run_build_job(job_id)
        return {"id": job.pk, "status": job.status, "image": job.built_image_ref}
    except Exception as exc:  # noqa: BLE001
        logger.exception("execute_docker_build %s", job_id)
        return {"id": job_id, "status": "failed", "error": str(exc)}


@shared_task(name="docker_mgmt.execute_docker_compose", bind=True, max_retries=0)
def execute_docker_compose(self, project_id: int, action: str) -> dict:
    from apps.docker_mgmt.build_compose import run_compose_action

    try:
        project = run_compose_action(project_id, action)
        return {"id": project.pk, "status": project.status, "action": action}
    except Exception as exc:  # noqa: BLE001
        logger.exception("execute_docker_compose %s %s", project_id, action)
        return {"id": project_id, "status": "error", "error": str(exc)}
