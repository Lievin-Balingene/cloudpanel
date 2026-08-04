"""Services Kubernetes: kubectl wrapper + aperçu cluster."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

from apps.core.exceptions import VZoneAPIException


def provision_mode() -> str:
    mode = (getattr(settings, "VZONE_K8S_PROVISION_MODE", "auto") or "auto").lower()
    return mode if mode in {"auto", "live", "mock"} else "auto"


def kubectl_bin() -> str:
    configured = getattr(settings, "VZONE_KUBECTL_BIN", "") or ""
    return configured or "kubectl"


def should_execute() -> bool:
    mode = provision_mode()
    if mode == "mock":
        return False
    if mode == "live":
        return True
    return shutil.which(kubectl_bin()) is not None


def _run(cmd: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        stderr = getattr(exc, "stderr", None) or getattr(exc, "stdout", None) or str(exc)
        raise VZoneAPIException(
            detail=f"Échec commande Kubernetes: {str(stderr)[-1200:]}",
            code="k8s_command_failed",
            status_code=502,
        ) from exc


def _mock_resources() -> dict:
    return {
        "namespaces": [{"name": "default"}, {"name": "kube-system"}],
        "pods": [],
        "workloads": [],
    }


def list_resources() -> dict:
    if not should_execute():
        return _mock_resources()
    kubectl = kubectl_bin()
    ns = _run([kubectl, "get", "ns", "-o", "json"], timeout=30)
    pods = _run([kubectl, "get", "pods", "-A", "-o", "json"], timeout=45)
    wk = _run([kubectl, "get", "deploy,sts,ds", "-A", "-o", "json"], timeout=45)
    nsj = json.loads(ns.stdout or "{}")
    podj = json.loads(pods.stdout or "{}")
    wkj = json.loads(wk.stdout or "{}")
    return {
        "namespaces": [
            {
                "name": i.get("metadata", {}).get("name", ""),
                "status": i.get("status", {}).get("phase", "Active"),
            }
            for i in nsj.get("items", [])
        ],
        "pods": [
            {
                "name": i.get("metadata", {}).get("name", ""),
                "namespace": i.get("metadata", {}).get("namespace", ""),
                "status": i.get("status", {}).get("phase", ""),
                "node": i.get("spec", {}).get("nodeName", ""),
            }
            for i in podj.get("items", [])
        ],
        "workloads": [
            {
                "name": i.get("metadata", {}).get("name", ""),
                "namespace": i.get("metadata", {}).get("namespace", ""),
                "kind": i.get("kind", ""),
                "ready": f"{i.get('status', {}).get('readyReplicas', 0)}/{i.get('status', {}).get('replicas', 0)}",
            }
            for i in wkj.get("items", [])
        ],
    }


def overview_for() -> dict:
    resources = list_resources()
    ok = 0
    bad = 0
    for p in resources["pods"]:
        if p["status"] == "Running":
            ok += 1
        else:
            bad += 1
    return {
        "provision_mode": provision_mode(),
        "kubectl_available": bool(shutil.which(kubectl_bin()) or Path(kubectl_bin()).exists()),
        "namespaces": len(resources["namespaces"]),
        "pods": len(resources["pods"]),
        "workloads": len(resources["workloads"]),
        "pods_running": ok,
        "pods_non_running": bad,
    }


def _apply_like(manifest: str, namespace: str, action: str) -> dict:
    if not manifest.strip():
        raise VZoneAPIException(detail="Manifest YAML requis.", code="manifest_required", status_code=400)
    if not should_execute():
        return {"ok": True, "output": f"{action} mock (pas de cluster live)."}
    kubectl = kubectl_bin()
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as tf:
        tf.write(manifest)
        path = tf.name
    try:
        cmd = [kubectl, action, "-f", path]
        if namespace.strip():
            cmd.extend(["-n", namespace.strip()])
        result = _run(cmd, timeout=120)
        return {"ok": True, "output": (result.stdout or result.stderr or "").strip()}
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def apply_manifest(manifest: str, namespace: str = "") -> dict:
    return _apply_like(manifest, namespace, "apply")


def delete_manifest(manifest: str, namespace: str = "") -> dict:
    return _apply_like(manifest, namespace, "delete")
