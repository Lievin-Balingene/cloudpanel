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

_KUBECTL_FALLBACKS = (
    "/usr/local/bin/kubectl",
    "/usr/bin/kubectl",
    "/snap/bin/kubectl",
    "/opt/bin/kubectl",
)
_SYSTEM_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin"


def provision_mode() -> str:
    mode = (getattr(settings, "VZONE_K8S_PROVISION_MODE", "auto") or "auto").lower()
    return mode if mode in {"auto", "live", "mock"} else "auto"


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{_SYSTEM_PATH}:{env.get('PATH', '')}"
    # kubeconfig k3s (si présent) pour les appels live
    k3s_cfg = "/etc/rancher/k3s/k3s.yaml"
    if not env.get("KUBECONFIG") and Path(k3s_cfg).is_file():
        env["KUBECONFIG"] = k3s_cfg
    return env


def _is_executable(path: str | Path) -> bool:
    try:
        p = Path(path)
        return p.is_file() and os.access(p, os.X_OK)
    except OSError:
        return False


def _which(name: str, *, search_path: str | None = None) -> str | None:
    if search_path:
        for directory in search_path.split(os.pathsep):
            if not directory:
                continue
            candidate = Path(directory) / name
            if _is_executable(candidate):
                return str(candidate.resolve())
        return None
    found = shutil.which(name, path=search_path or _subprocess_env()["PATH"])
    return str(Path(found).resolve()) if found else None


def kubectl_bin() -> str:
    """Résout le binaire kubectl (PATH systemd souvent minimal pour vzone-api)."""
    configured = (getattr(settings, "VZONE_KUBECTL_BIN", "") or "").strip()
    path = _subprocess_env()["PATH"]
    ordered: list[str] = []
    if configured:
        ordered.append(configured)
    ordered.extend(_KUBECTL_FALLBACKS)
    ordered.append("kubectl")

    seen: set[str] = set()
    for candidate in ordered:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if candidate.startswith("/") or (len(candidate) > 1 and candidate[1] == ":"):
            if _is_executable(candidate):
                return str(Path(candidate).resolve())
            continue
        found = _which(candidate, search_path=path)
        if found:
            return found

    # Dernier recours : chemins connus même si settings pointe vers "kubectl" relatif
    for fallback in _KUBECTL_FALLBACKS:
        if _is_executable(fallback):
            return str(Path(fallback).resolve())
    return configured or "kubectl"


def kubectl_available() -> bool:
    path = kubectl_bin()
    if _is_executable(path):
        return True
    return _which(Path(path).name, search_path=_subprocess_env()["PATH"]) is not None


def should_execute() -> bool:
    mode = provision_mode()
    if mode == "mock":
        return False
    if mode == "live":
        return True
    return kubectl_available()


def _run(cmd: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_subprocess_env(),
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
        "kubectl_available": kubectl_available(),
        "kubectl_bin": kubectl_bin(),
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
