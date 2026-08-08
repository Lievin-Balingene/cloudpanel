"""Tickets courts pour terminal WS + rootterm (pas de JWT long en query string)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from django.conf import settings

from apps.core.exceptions import VZoneAPIException

ROOTTERM_TICKETS = Path(
    getattr(settings, "VZONE_ROOTTERM_TICKETS_DIR", "/var/lib/vzone/terminal/tickets")
)


def _secret() -> bytes:
    raw = (
        getattr(settings, "VZONE_TERMINAL_TICKET_SECRET", None)
        or getattr(settings, "SECRET_KEY", "")
        or "vzone-dev"
    )
    return str(raw).encode("utf-8")


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    import base64

    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def issue_ws_ticket(*, user_id: int, mode: str, ttl_sec: int | None = None) -> dict:
    """Ticket one-shot (en pratique TTL court) pour WebSocket /ws/terminal/."""
    ttl = int(ttl_sec or getattr(settings, "VZONE_TERMINAL_TICKET_TTL", 60))
    now = int(time.time())
    payload = {
        "uid": int(user_id),
        "mode": mode if mode in {"root", "jail"} else "jail",
        "exp": now + max(15, min(ttl, 120)),
        "nbf": now - 5,
        "jti": secrets.token_hex(16),
    }
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = _b64url(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return {
        "ticket": f"{body}.{sig}",
        "expires_in": payload["exp"] - now,
        "mode": payload["mode"],
    }


def consume_ws_ticket(ticket: str) -> dict:
    """Valide le ticket WS. Retourne {uid, mode}."""
    raw = (ticket or "").strip()
    if not raw or raw.count(".") != 1:
        raise VZoneAPIException(detail="Ticket terminal invalide.", code="bad_ticket", status_code=401)
    body, sig = raw.split(".", 1)
    expected = _b64url(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        raise VZoneAPIException(detail="Ticket terminal invalide.", code="bad_ticket", status_code=401)
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise VZoneAPIException(detail="Ticket terminal invalide.", code="bad_ticket", status_code=401) from exc
    now = int(time.time())
    if int(payload.get("exp", 0)) < now or int(payload.get("nbf", 0)) > now:
        raise VZoneAPIException(detail="Ticket terminal expiré.", code="ticket_expired", status_code=401)
    uid = int(payload.get("uid", 0))
    if uid <= 0:
        raise VZoneAPIException(detail="Ticket terminal invalide.", code="bad_ticket", status_code=401)
    mode = payload.get("mode") if payload.get("mode") in {"root", "jail"} else "jail"
    return {"uid": uid, "mode": mode, "jti": str(payload.get("jti") or "")}


def issue_rootterm_ticket_file() -> Path:
    """
    Crée un fichier ticket one-shot pour vzone-rootterm --ticket.
    Doit être appelé juste avant le spawn PTY (admin uniquement).
    """
    ROOTTERM_TICKETS.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(ROOTTERM_TICKETS, 0o700)
    except OSError:
        pass
    name = secrets.token_hex(16)
    path = ROOTTERM_TICKETS / name
    # Contenu opaque (nonce) — le helper vérifie taille + âge + path
    path.write_bytes(secrets.token_bytes(32))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path
