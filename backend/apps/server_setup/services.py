"""Services hostname OS + nameservers par défaut."""
from __future__ import annotations

import json
import re
import secrets
import socket
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.core.exceptions import VZoneAPIException
from apps.server_setup.models import ServerSetup

HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$",
    re.IGNORECASE,
)
NS_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+\.?$",
    re.IGNORECASE,
)


def jobs_dir() -> Path:
    root = Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "hostname" / "jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def current_os_hostname() -> str:
    try:
        return socket.getfqdn() or socket.gethostname()
    except OSError:
        return socket.gethostname()


def normalize_hostname(value: str) -> str:
    host = (value or "").strip().lower().rstrip(".")
    if not host or not HOSTNAME_RE.match(host):
        raise VZoneAPIException(
            detail="Hostname invalide (FQDN requis, ex: server.example.com).",
            code="invalid_hostname",
            status_code=400,
        )
    if "." not in host:
        raise VZoneAPIException(
            detail="Le hostname doit être un FQDN (au moins un point).",
            code="invalid_hostname",
            status_code=400,
        )
    return host


def normalize_nameserver(value: str, *, required: bool = False) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        if required:
            raise VZoneAPIException(
                detail="Nameserver requis.",
                code="invalid_nameserver",
                status_code=400,
            )
        return ""
    if not NS_RE.match(raw):
        raise VZoneAPIException(
            detail=f"Nameserver invalide: {value}",
            code="invalid_nameserver",
            status_code=400,
        )
    return raw if raw.endswith(".") else f"{raw}."


def default_nameservers() -> tuple[str, str, str, str]:
    setup = ServerSetup.get_solo()
    ns1 = (setup.nameserver1 or "").strip()
    ns2 = (setup.nameserver2 or "").strip()
    ns3 = (setup.nameserver3 or "").strip()
    ns4 = (setup.nameserver4 or "").strip()
    if ns1 and not ns1.endswith("."):
        ns1 = f"{ns1}."
    if ns2 and not ns2.endswith("."):
        ns2 = f"{ns2}."
    if ns3 and not ns3.endswith("."):
        ns3 = f"{ns3}."
    if ns4 and not ns4.endswith("."):
        ns4 = f"{ns4}."
    return ns1, ns2, ns3, ns4


def get_setup_payload() -> dict:
    setup = ServerSetup.get_solo()
    os_host = current_os_hostname()
    if not setup.hostname:
        setup.hostname = os_host
        setup.save(update_fields=["hostname", "updated_at"])
    public_ip = (getattr(settings, "VZONE_PUBLIC_IP", "") or "").strip()
    return {
        "hostname": setup.hostname,
        "os_hostname": os_host,
        "nameserver1": setup.nameserver1,
        "nameserver2": setup.nameserver2,
        "nameserver3": setup.nameserver3,
        "nameserver4": setup.nameserver4,
        "resolver1": setup.resolver1,
        "resolver2": setup.resolver2,
        "contact_email": setup.contact_email,
        "apply_hostname_to_mail": setup.apply_hostname_to_mail,
        "public_ip": public_ip,
        "hostname_applied_at": setup.hostname_applied_at.isoformat() if setup.hostname_applied_at else None,
        "last_hostname_error": setup.last_hostname_error,
        "updated_at": setup.updated_at.isoformat() if setup.updated_at else None,
    }


def _enqueue_hostname_job(
    hostname: str,
    *,
    apply_mail: bool,
    public_ip: str,
    wait: bool = False,
    wait_seconds: float = 90,
) -> dict:
    """
    Lance l'agent root en arrière-plan.
    wait=False (défaut) : ne bloque pas la requête HTTP — évite Failed to fetch
    quand nginx reload coupe la connexion pendant ensure-nginx.
    """
    jobs = jobs_dir()
    job_id = secrets.token_hex(12)
    request = jobs / f"{job_id}.request"
    result_path = jobs / f"{job_id}.result"
    payload = {
        "hostname": hostname,
        "apply_mail": apply_mail,
        "public_ip": public_ip,
    }
    tmp = jobs / f"{job_id}.request.tmp"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(request)

    try:
        subprocess.run(
            ["systemctl", "start", "vzone-hostname-job.service"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    if not wait:
        return {
            "ok": True,
            "pending": True,
            "job_id": job_id,
            "hostname": hostname,
            "message": "Hostname en cours d'application en arrière-plan.",
        }

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if result_path.is_file():
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {"ok": False, "error": "Résultat hostname illisible"}
            try:
                result_path.unlink(missing_ok=True)
            except OSError:
                pass
            return data if isinstance(data, dict) else {"ok": False, "error": "Résultat invalide"}
        time.sleep(0.3)

    raise VZoneAPIException(
        detail=(
            "Timeout application hostname (agent root). "
            "Vérifiez: systemctl status vzone-hostname-job.path vzone-hostname-job.service"
        ),
        code="hostname_timeout",
        status_code=504,
    )


def update_setup(
    *,
    hostname: str | None = None,
    nameserver1: str | None = None,
    nameserver2: str | None = None,
    nameserver3: str | None = None,
    nameserver4: str | None = None,
    resolver1: str | None = None,
    resolver2: str | None = None,
    contact_email: str | None = None,
    apply_hostname_to_mail: bool | None = None,
    apply_hostname: bool = False,
) -> dict:
    setup = ServerSetup.get_solo()
    hostname_result: dict | None = None
    previous_hostname = (setup.hostname or "").strip().lower()

    if nameserver1 is not None:
        setup.nameserver1 = normalize_nameserver(nameserver1, required=True)
    if nameserver2 is not None:
        setup.nameserver2 = normalize_nameserver(nameserver2, required=True)
    if nameserver3 is not None:
        setup.nameserver3 = normalize_nameserver(nameserver3) if nameserver3.strip() else ""
    if nameserver4 is not None:
        setup.nameserver4 = normalize_nameserver(nameserver4) if nameserver4.strip() else ""
    if resolver1 is not None:
        setup.resolver1 = resolver1 or None
    if resolver2 is not None:
        setup.resolver2 = resolver2 or None
    if contact_email is not None:
        setup.contact_email = (contact_email or "").strip()
    if apply_hostname_to_mail is not None:
        setup.apply_hostname_to_mail = bool(apply_hostname_to_mail)

    new_hostname = None
    if hostname is not None and hostname.strip():
        new_hostname = normalize_hostname(hostname)
        setup.hostname = new_hostname

    # Persist NS / metadata first — source of truth, réponse HTTP immédiate.
    setup.save()

    # N'appliquer l'OS hostname que si demandé ET réellement changé.
    hostname_changed = bool(
        new_hostname
        and new_hostname != previous_hostname
        and new_hostname != current_os_hostname().lower().rstrip(".")
    )
    if new_hostname and apply_hostname and hostname_changed:
        public_ip = (getattr(settings, "VZONE_PUBLIC_IP", "") or "").strip()
        try:
            # Async : ne pas attendre (nginx reload tuait la requête → Failed to fetch)
            hostname_result = _enqueue_hostname_job(
                new_hostname,
                apply_mail=setup.apply_hostname_to_mail,
                public_ip=public_ip,
                wait=False,
            )
            setup.last_hostname_error = ""
            setup.hostname_applied_at = timezone.now()
            setup.save(update_fields=["last_hostname_error", "hostname_applied_at", "updated_at"])
        except VZoneAPIException:
            raise
        except Exception as exc:  # noqa: BLE001
            setup.last_hostname_error = str(exc)
            setup.save(update_fields=["last_hostname_error", "updated_at"])
            raise VZoneAPIException(
                detail=f"Impossible de lancer l'application du hostname: {exc}",
                code="hostname_apply_failed",
                status_code=502,
            ) from exc
    elif new_hostname and apply_hostname and not hostname_changed:
        hostname_result = {
            "ok": True,
            "skipped": True,
            "hostname": new_hostname,
            "message": "Hostname inchangé — nameservers enregistrés.",
        }

    payload = get_setup_payload()
    payload["hostname_apply"] = hostname_result
    return payload
