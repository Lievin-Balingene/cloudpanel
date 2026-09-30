"""Validation d'URL BYOK — anti-SSRF (pas de localhost / RFC1918 sauf opt-in)."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings

from apps.core.exceptions import VZoneAPIException

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
    }
)


def byok_allow_private() -> bool:
    return bool(getattr(settings, "VZONE_AI_BYOK_ALLOW_PRIVATE_URLS", False))


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return True
    if ip.is_multicast or ip.is_unspecified:
        return True
    # Cloud metadata
    if isinstance(ip, ipaddress.IPv4Address) and str(ip) in {"169.254.169.254", "100.100.100.200"}:
        return True
    return False


def validate_byok_url(raw: str) -> str:
    """
    Normalise et valide une URL BYOK.
    Retourne l'URL sans slash final (sauf si path=/ seul).
    """
    url = (raw or "").strip()
    if not url:
        raise VZoneAPIException(
            detail="URL du provider requise.",
            code="byok_url_required",
            status_code=400,
        )
    if len(url) > 512:
        raise VZoneAPIException(
            detail="URL trop longue (max 512).",
            code="byok_url_too_long",
            status_code=400,
        )
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise VZoneAPIException(
            detail="URL invalide : utilisez http:// ou https://",
            code="byok_url_scheme",
            status_code=400,
        )
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise VZoneAPIException(
            detail="Hostname manquant dans l'URL.",
            code="byok_url_host",
            status_code=400,
        )
    if host in _BLOCKED_HOSTNAMES and not byok_allow_private():
        raise VZoneAPIException(
            detail="URL locale interdite (SSRF). Exposez Ollama via un tunnel HTTPS public, "
            "ou demandez à l'admin VZONE_AI_BYOK_ALLOW_PRIVATE_URLS=true.",
            code="byok_url_private",
            status_code=400,
        )
    # IP littérale
    try:
        ip = ipaddress.ip_address(host)
        if _is_blocked_ip(ip) and not byok_allow_private():
            raise VZoneAPIException(
                detail="Adresse IP privée / loopback interdite (SSRF).",
                code="byok_url_private",
                status_code=400,
            )
    except ValueError:
        # Hostname : résoudre et vérifier les A/AAAA
        if not byok_allow_private():
            try:
                infos = socket.getaddrinfo(host, parsed.port or (443 if scheme == "https" else 80))
            except socket.gaierror as exc:
                raise VZoneAPIException(
                    detail=f"Hostname non résolvable: {host}",
                    code="byok_url_dns",
                    status_code=400,
                ) from exc
            for info in infos:
                addr = info[4][0]
                try:
                    ip = ipaddress.ip_address(addr)
                except ValueError:
                    continue
                if _is_blocked_ip(ip):
                    raise VZoneAPIException(
                        detail=f"Le hostname {host} résout vers une IP privée ({addr}) — interdit.",
                        code="byok_url_private",
                        status_code=400,
                    )

    # Recompose sans credentials dans l'URL
    if parsed.username or parsed.password:
        raise VZoneAPIException(
            detail="Ne mettez pas user:pass dans l'URL — utilisez le champ clé API.",
            code="byok_url_creds",
            status_code=400,
        )
    normalized = f"{scheme}://{host}"
    if parsed.port:
        normalized += f":{parsed.port}"
    path = parsed.path or ""
    if path and path != "/":
        normalized += path.rstrip("/")
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized
