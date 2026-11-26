"""Résolution du jeton et contrôle d'accès."""
from __future__ import annotations

import ipaddress
import re

from django.utils import timezone

from apps.panel_api.models import ApiToken, hash_api_token

_AUTH = re.compile(r"^(?:whm|cpanel|anga)\s+(\S+):(\S+)\s*$", re.IGNORECASE)


class TokenAuthError(Exception):
    def __init__(self, reason: str, status: int = 401) -> None:
        self.reason = reason
        self.status = status
        super().__init__(reason)


def _ip_allowed(token: ApiToken, ip: str | None) -> bool:
    raw = (token.ip_allowlist or "").strip()
    if not raw:
        return True
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for part in re.split(r"[\s,;]+", raw):
        if not part:
            continue
        try:
            if "/" in part:
                if addr in ipaddress.ip_network(part, strict=False):
                    return True
            elif addr == ipaddress.ip_address(part):
                return True
        except ValueError:
            continue
    return False


def parse_credentials(request) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    header = request.META.get("HTTP_AUTHORIZATION") or ""
    match = _AUTH.match(header.strip())
    if match:
        return match.group(1), match.group(2)
    # Bearer vzapi_… (sans nom d'utilisateur — le jeton est unique)
    if header.lower().startswith("bearer "):
        raw = header.split(" ", 1)[1].strip()
        if raw.startswith("vzapi_"):
            return "", raw
    # Pas de jeton dans l'URL : il finirait dans les journaux, l'historique et le Referer.
    raise TokenAuthError(
        "Jeton requis. En-tête Authorization: whm utilisateur:JETON "
        "ou cpanel utilisateur:JETON ou anga utilisateur:JETON."
    )


def authenticate_token(request) -> ApiToken:  # type: ignore[no-untyped-def]
    from apps.security.services import client_ip

    username, raw = parse_credentials(request)
    token = (
        ApiToken.objects.select_related("user")
        .filter(token_hash=hash_api_token(raw))
        .first()
    )
    if token is None or not token.is_active:
        raise TokenAuthError("Jeton invalide, révoqué ou expiré.")
    if username and token.user.username != username:
        raise TokenAuthError("Le nom d'utilisateur ne correspond pas au jeton.")
    user = token.user
    if not user.is_active or user.is_suspended:
        raise TokenAuthError("Compte indisponible.", status=403)
    ip = client_ip(request)
    if not _ip_allowed(token, ip):
        raise TokenAuthError("Adresse IP non autorisée pour ce jeton.", status=403)
    token.touch(ip)
    return token


def reject_if_expired_note(token: ApiToken) -> None:
    if token.expires_at and token.expires_at <= timezone.now():
        raise TokenAuthError("Jeton expiré.")
