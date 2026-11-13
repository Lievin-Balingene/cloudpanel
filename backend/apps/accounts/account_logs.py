"""Journaux web par compte / domaine (nginx + OpenLiteSpeed) — style cPanel Raw Access / Error Log."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone as dt_tz
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException

SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")

KIND_SPECS: tuple[tuple[str, str, str, Path], ...] = (
    # kind, engine, label_suffix, path_template relative builder
)


def _safe_prefix(domain_name: str) -> str:
    return SAFE_NAME_RE.sub("_", (domain_name or "").lower())


def _log_candidates(domain_name: str) -> list[dict[str, Any]]:
    prefix = _safe_prefix(domain_name)
    nginx_dir = Path("/var/log/nginx")
    ols_dir = Path(getattr(settings, "VZONE_DATA_ROOT", Path("/var/lib/vzone"))) / "ols" / "logs"
    specs = [
        ("access", "nginx", "Access (HTTP)", nginx_dir / f"{prefix}.access.log"),
        ("error", "nginx", "Error (HTTP)", nginx_dir / f"{prefix}.error.log"),
        ("ssl_access", "nginx", "Access (HTTPS)", nginx_dir / f"{prefix}.ssl.access.log"),
        ("ssl_error", "nginx", "Error (HTTPS)", nginx_dir / f"{prefix}.ssl.error.log"),
        ("ols_access", "ols", "Access (OLS)", ols_dir / f"{prefix}.access.log"),
        ("ols_error", "ols", "Error (OLS)", ols_dir / f"{prefix}.error.log"),
    ]
    out: list[dict[str, Any]] = []
    for kind, engine, label, path in specs:
        exists = False
        size = 0
        mtime = None
        try:
            if path.is_file():
                st = path.stat()
                exists = True
                size = int(st.st_size)
                mtime = datetime.fromtimestamp(st.st_mtime, tz=dt_tz.utc).isoformat()
        except OSError:
            exists = False
        out.append(
            {
                "kind": kind,
                "engine": engine,
                "label": label,
                "domain": domain_name,
                "path": str(path),
                "exists": exists,
                "size_bytes": size,
                "modified_at": mtime,
            }
        )
    return out


def list_account_logs(owner: User) -> dict[str, Any]:
    from apps.domains.models import Domain

    domains = list(
        Domain.objects.filter(owner=owner, is_active=True)
        .order_by("name")
        .values_list("id", "name", "domain_type")
    )
    domain_rows = []
    for domain_id, name, dtype in domains:
        logs = _log_candidates(name)
        domain_rows.append(
            {
                "id": domain_id,
                "name": name,
                "domain_type": dtype,
                "logs": logs,
                "available_count": sum(1 for L in logs if L["exists"]),
            }
        )
    return {
        "username": owner.username,
        "user_id": owner.pk,
        "domains": domain_rows,
        "total_available": sum(d["available_count"] for d in domain_rows),
    }


def _resolve_log_path(owner: User, domain_name: str, kind: str) -> Path:
    from apps.domains.models import Domain

    domain_name = (domain_name or "").strip().lower()
    kind = (kind or "access").strip().lower()
    if not Domain.objects.filter(owner=owner, name__iexact=domain_name).exists():
        raise VZoneAPIException(
            detail="Domaine introuvable pour ce compte.",
            code="domain_not_found",
            status_code=404,
        )
    candidates = {c["kind"]: Path(c["path"]) for c in _log_candidates(domain_name)}
    path = candidates.get(kind)
    if path is None:
        raise VZoneAPIException(
            detail=f"Type de journal inconnu: {kind}",
            code="invalid_log_kind",
            status_code=400,
        )
    # Anti path-traversal : uniquement chemins calculés
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise VZoneAPIException(
            detail="Chemin journal inaccessible.",
            code="log_unreadable",
            status_code=400,
        ) from exc
    allowed_roots = [
        Path("/var/log/nginx").resolve(),
        (Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "ols" / "logs").resolve(),
    ]
    if not any(str(resolved).startswith(str(root) + os.sep) or resolved == root for root in allowed_roots):
        raise VZoneAPIException(
            detail="Chemin journal hors zone autorisée.",
            code="log_forbidden",
            status_code=403,
        )
    return resolved


def tail_account_log(
    owner: User,
    *,
    domain_name: str,
    kind: str = "access",
    lines: int = 200,
    max_bytes: int = 512 * 1024,
) -> dict[str, Any]:
    lines = max(10, min(int(lines), 2000))
    max_bytes = max(16 * 1024, min(int(max_bytes), 2 * 1024 * 1024))
    path = _resolve_log_path(owner, domain_name, kind)
    if not path.is_file():
        return {
            "domain": domain_name,
            "kind": kind,
            "path": str(path),
            "exists": False,
            "lines": [],
            "line_count": 0,
            "size_bytes": 0,
            "truncated": False,
        }
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            data = handle.read()
    except OSError as exc:
        raise VZoneAPIException(
            detail=f"Lecture impossible: {exc}",
            code="log_unreadable",
            status_code=500,
        ) from exc

    truncated = size > max_bytes
    if truncated:
        data = data.split(b"\n", 1)[-1]
    text_lines = data.decode("utf-8", errors="replace").splitlines()
    if len(text_lines) > lines:
        text_lines = text_lines[-lines:]
        truncated = True

    return {
        "domain": domain_name,
        "kind": kind,
        "path": str(path),
        "exists": True,
        "lines": text_lines,
        "line_count": len(text_lines),
        "size_bytes": size,
        "truncated": truncated,
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=dt_tz.utc).isoformat(),
    }
