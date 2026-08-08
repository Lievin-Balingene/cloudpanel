"""Validation Git : branches (anti injection d'options) + URLs (anti-SSRF)."""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from apps.core.exceptions import VZoneAPIException

# Pas de '-' en tête (options git), pas d'espaces / métacaractères shell
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,127}$")

# Hôtes Git publics usuels (SSH) — IP littérales privées refusées ailleurs
_SSH_HOST_RE = re.compile(
    r"^git@([A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)[:/].+",
    re.IGNORECASE,
)


def validate_git_branch(branch: str) -> str:
    value = (branch or "").strip() or "main"
    if value.startswith("-") or ".." in value or value.startswith("/") or "\\" in value:
        raise VZoneAPIException(
            detail="Nom de branche Git invalide.",
            code="invalid_branch",
            status_code=400,
        )
    if not BRANCH_RE.fullmatch(value):
        raise VZoneAPIException(
            detail="Nom de branche Git invalide.",
            code="invalid_branch",
            status_code=400,
        )
    return value


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _assert_host_safe(host: str) -> None:
    hostname = (host or "").strip().lower().rstrip(".")
    if not hostname:
        raise VZoneAPIException(detail="URL Git invalide.", code="invalid_url", status_code=400)
    if hostname in {"localhost", "metadata.google.internal"}:
        raise VZoneAPIException(
            detail="Hôte Git interdit (SSRF).",
            code="ssrf_blocked",
            status_code=400,
        )
    # IP littérale
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_blocked_ip(ip):
            raise VZoneAPIException(
                detail="Hôte Git interdit (SSRF).",
                code="ssrf_blocked",
                status_code=400,
            )
        return
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise VZoneAPIException(
            detail="Impossible de résoudre l'hôte Git.",
            code="dns_failed",
            status_code=400,
        ) from exc
    if not infos:
        raise VZoneAPIException(
            detail="Impossible de résoudre l'hôte Git.",
            code="dns_failed",
            status_code=400,
        )
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise VZoneAPIException(
                detail="Hôte Git interdit (SSRF).",
                code="ssrf_blocked",
                status_code=400,
            )


def validate_git_remote_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise VZoneAPIException(detail="URL Git invalide.", code="invalid_url", status_code=400)

    if value.startswith("git@"):
        m = _SSH_HOST_RE.match(value)
        if not m:
            raise VZoneAPIException(detail="URL Git SSH invalide.", code="invalid_url", status_code=400)
        _assert_host_safe(m.group(1))
        return value

    if value.startswith("ssh://"):
        parsed = urlparse(value)
        if not parsed.hostname:
            raise VZoneAPIException(detail="URL Git invalide.", code="invalid_url", status_code=400)
        _assert_host_safe(parsed.hostname)
        return value

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise VZoneAPIException(detail="URL Git invalide.", code="invalid_url", status_code=400)
        if parsed.username or parsed.password:
            # Évite credentials@host ambiguës / injection
            raise VZoneAPIException(
                detail="URL Git avec credentials intégrés refusée — utilisez une deploy key.",
                code="invalid_url",
                status_code=400,
            )
        _assert_host_safe(parsed.hostname)
        return value

    raise VZoneAPIException(detail="URL Git invalide.", code="invalid_url", status_code=400)
