"""Notifications WHM style cPanel — Contact Manager (email admin)."""
from __future__ import annotations

import logging
import socket
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

# Clés tweak_settings (Contact Manager)
EVENT_ACCOUNT_CREATION = "notify_account_creation"
EVENT_ACCOUNT_SUSPEND = "notify_account_suspend"
EVENT_ACCOUNT_TERMINATION = "notify_account_termination"
EVENT_PASSWORD_RESET = "notify_password_reset"
EVENT_BACKUP_FAILURE = "backup_notify_email"

DEFAULT_EVENTS = {
    EVENT_ACCOUNT_CREATION: True,
    EVENT_ACCOUNT_SUSPEND: True,
    EVENT_ACCOUNT_TERMINATION: True,
    EVENT_PASSWORD_RESET: True,
    EVENT_BACKUP_FAILURE: True,
}


def get_server_setup():
    from apps.server_setup.models import ServerSetup

    return ServerSetup.get_solo()


def get_contact_email() -> str | None:
    """Email admin WHM (Contact Manager) — priorité contact_email serveur."""
    setup = get_server_setup()
    email = (setup.contact_email or "").strip()
    if email and "@" in email:
        return email

    # Fallback : destinataires monitoring env
    default = (getattr(settings, "VZONE_ALERT_DEFAULT_RECIPIENTS", "") or "").strip()
    for part in default.split(","):
        part = part.strip()
        if part and "@" in part:
            return part

    # Fallback : premier admin panel
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        admin = (
            User.objects.filter(role="administrator", is_active=True)
            .exclude(email="")
            .order_by("id")
            .first()
        )
        if admin and admin.email and "@" in admin.email:
            # Persiste pour les prochaines alertes (comme cPanel Contact Manager)
            if not (setup.contact_email or "").strip():
                setup.contact_email = admin.email
                setup.save(update_fields=["contact_email", "updated_at"])
            return admin.email
    except Exception:  # noqa: BLE001
        logger.debug("resolve admin email failed", exc_info=True)
    return None


def ensure_contact_email(email: str | None = None) -> str | None:
    """Définit le contact admin si fourni ; sinon retourne le contact courant."""
    setup = get_server_setup()
    if email is not None:
        cleaned = (email or "").strip()
        setup.contact_email = cleaned
        setup.save(update_fields=["contact_email", "updated_at"])
        return cleaned or get_contact_email()
    return get_contact_email()


def is_event_enabled(event_key: str) -> bool:
    setup = get_server_setup()
    tweaks = setup.tweak_settings or {}
    if event_key in tweaks:
        return bool(tweaks[event_key])
    return bool(DEFAULT_EVENTS.get(event_key, True))


def panel_hostname() -> str:
    setup = get_server_setup()
    host = (setup.hostname or "").strip().rstrip(".")
    if host:
        return host
    try:
        return socket.getfqdn() or socket.gethostname()
    except OSError:
        return "localhost"


def public_ip() -> str:
    return (getattr(settings, "VZONE_PUBLIC_IP", "") or "").strip() or "—"


def reverse_dns(ip: str | None) -> str:
    if not ip:
        return "—"
    try:
        name, _alias, _ips = socket.gethostbyaddr(ip)
        return name or "—"
    except (socket.herror, socket.gaierror, OSError):
        return "—"


def request_meta(request) -> dict[str, str]:  # type: ignore[no-untyped-def]
    from apps.security.services import client_ip

    ip = ""
    try:
        ip = (client_ip(request) or "").strip()
    except Exception:  # noqa: BLE001
        ip = (getattr(request, "META", {}) or {}).get("REMOTE_ADDR") or ""
    ua = (getattr(request, "META", {}) or {}).get("HTTP_USER_AGENT") or ""
    return {
        "ip": ip or "—",
        "rdns": reverse_dns(ip) if ip and ip != "—" else "—",
        "user_agent": ua[:240],
    }


def _from_email() -> str:
    contact = get_contact_email()
    host = panel_hostname()
    configured = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if configured and "@" in configured and "localhost" not in configured.lower():
        return configured
    if contact:
        # Prefer noreply@hostname for automated notices
        return f"noreply@{host}" if "." in host else contact
    return configured or f"noreply@{host}"


def send_whm_notice(
    *,
    event_key: str,
    subject: str,
    body: str,
    importance: str = "Low",
) -> bool:
    if not is_event_enabled(event_key):
        logger.info("Notice %s désactivée (Tweak Settings)", event_key)
        return False
    to = get_contact_email()
    if not to:
        logger.warning("Aucun contact_email WHM — notice %s non envoyée", event_key)
        return False
    host = panel_hostname()
    admin_port = getattr(settings, "VZONE_ADMIN_PORT", 9086)
    footer = (
        f"\n"
        f"The system generated this notice on {datetime.now(dt_timezone.utc).strftime('%A, %B %d, %Y at %I:%M:%S %p UTC')}.\n"
        f"\n"
        f"“{subject.split('—')[0].strip()}” notifications are currently configured to have an importance of “{importance}”. "
        f"You can change notification settings in WHM’s Contact Manager / Tweak Settings at: "
        f"https://{host}:{admin_port}/whm/tweak-settings\n"
        f"\n"
        f"Do not reply to this automated message.\n"
        f"\n"
        f"AngaPanel\n"
    )
    full = body.rstrip() + "\n" + footer
    try:
        send_mail(
            subject=subject,
            message=full,
            from_email=_from_email(),
            recipient_list=[to],
            fail_silently=False,
        )
        logger.info("WHM notice %s envoyée à %s", event_key, to)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Échec envoi notice WHM %s → %s", event_key, to)
        return False


def _account_package_name(user) -> str:  # type: ignore[no-untyped-def]
    try:
        from apps.packages.models import PackageAssignment

        asg = (
            PackageAssignment.objects.filter(user=user)
            .select_related("package")
            .order_by("-id")
            .first()
        )
        if asg and asg.package_id:
            return asg.package.name
    except Exception:  # noqa: BLE001
        pass
    return "—"


def _account_domain(user) -> str:  # type: ignore[no-untyped-def]
    try:
        from apps.domains.models import Domain

        d = (
            Domain.objects.filter(owner=user, domain_type=Domain.DomainType.PRIMARY)
            .order_by("id")
            .first()
            or Domain.objects.filter(owner=user).order_by("id").first()
        )
        if d:
            return d.name
    except Exception:  # noqa: BLE001
        pass
    return "—"


def _quota_label(user) -> str:  # type: ignore[no-untyped-def]
    try:
        q = getattr(user, "quota", None)
        if not q:
            return "—"
        disk = getattr(q, "disk_mb", None)
        if disk is None or int(disk) <= 0:
            return "Unlimited"
        return f"{int(disk)} MB"
    except Exception:  # noqa: BLE001
        return "—"


def notify_account_creation(
    user,
    *,
    actor=None,
    request=None,
    package_name: str | None = None,
) -> bool:
    """Email admin style cPanel « Account Creation »."""
    meta = request_meta(request) if request is not None else {"ip": "—", "rdns": "—", "user_agent": ""}
    actor_name = getattr(actor, "username", None) or "system"
    domain = _account_domain(user)
    pkg = package_name or _account_package_name(user)
    ip = public_ip()
    home_root = str(getattr(settings, "VZONE_HOME_ROOT", "/home"))
    cgi = "Enabled"  # comportement panel actuel
    theme = "angapanel"
    locale = "en"

    body = (
        f"Domain:\t{domain}\n"
        f"IP Address:\t{ip} (Shared)\n"
        f"CGI Access:\t{cgi}\n"
        f"Username:\t{user.username}\n"
        f"Password:\t***HIDDEN***\n"
        f"Panel Theme:\t{theme}\n"
        f"Home Directory Root:\t{home_root}\n"
        f"Home Directory:\t{user.home_directory or f'{home_root}/{user.username}'}\n"
        f"Quota:\t{_quota_label(user)}\n"
        f"Contact Email:\t{user.email}\n"
        f"Package:\t{pkg}\n"
        f"Feature List:\tdefault\n"
        f"Locale:\t{locale}\n"
        f"“{actor_name}” set up the account.\n"
        f"\n"
        f"This notice is the result of a request made by a computer with the IP address of "
        f"“{meta['ip']}” through the “WHM” service on the server while logged in as “{actor_name}”.\n"
        f"\n"
        f"A reverse DNS lookup on the remote IP address returned the host name “{meta['rdns']}”.\n"
    )
    if meta.get("user_agent"):
        body += f"\nUser-Agent: {meta['user_agent']}\n"

    subject = f"Account Creation — {user.username}@{panel_hostname()}"
    return send_whm_notice(
        event_key=EVENT_ACCOUNT_CREATION,
        subject=subject,
        body=body,
        importance="Low",
    )


def notify_account_suspend(user, *, actor=None, request=None, suspended: bool = True) -> bool:
    action = "Account Suspension" if suspended else "Account Unsuspension"
    meta = request_meta(request) if request is not None else {"ip": "—", "rdns": "—"}
    actor_name = getattr(actor, "username", None) or "system"
    body = (
        f"Username:\t{user.username}\n"
        f"Domain:\t{_account_domain(user)}\n"
        f"Contact Email:\t{user.email}\n"
        f"Action:\t{'Suspended' if suspended else 'Unsuspended'}\n"
        f"“{actor_name}” performed this action.\n"
        f"\n"
        f"Request IP: {meta['ip']} (rDNS: {meta['rdns']})\n"
        f"Service: WHM\n"
    )
    return send_whm_notice(
        event_key=EVENT_ACCOUNT_SUSPEND,
        subject=f"{action} — {user.username}@{panel_hostname()}",
        body=body,
        importance="Medium",
    )


def notify_password_reset(user, *, actor=None, request=None) -> bool:
    """Email admin — reset MDP (jamais le mot de passe en clair)."""
    meta = request_meta(request) if request is not None else {"ip": "—", "rdns": "—"}
    actor_name = getattr(actor, "username", None) or "system"
    body = (
        f"Username:\t{user.username}\n"
        f"Domain:\t{_account_domain(user)}\n"
        f"Contact Email:\t{user.email}\n"
        f"Password:\t***HIDDEN*** (temporary; must change on next login)\n"
        f"Sessions:\tall panel sessions revoked\n"
        f"“{actor_name}” reset the account password.\n"
        f"\n"
        f"Request IP: {meta['ip']} (rDNS: {meta['rdns']})\n"
        f"Service: WHM\n"
    )
    return send_whm_notice(
        event_key=EVENT_PASSWORD_RESET,
        subject=f"Password Reset — {user.username}@{panel_hostname()}",
        body=body,
        importance="Medium",
    )


def notify_account_termination(user, *, actor=None, request=None) -> bool:
    meta = request_meta(request) if request is not None else {"ip": "—", "rdns": "—"}
    actor_name = getattr(actor, "username", None) or "system"
    # Capture fields before delete
    username = user.username
    email = user.email
    domain = _account_domain(user)
    body = (
        f"Username:\t{username}\n"
        f"Domain:\t{domain}\n"
        f"Contact Email:\t{email}\n"
        f"Home Directory:\t{user.home_directory or '—'}\n"
        f"“{actor_name}” terminated the account.\n"
        f"\n"
        f"Request IP: {meta['ip']} (rDNS: {meta['rdns']})\n"
        f"Service: WHM\n"
    )
    return send_whm_notice(
        event_key=EVENT_ACCOUNT_TERMINATION,
        subject=f"Account Termination — {username}@{panel_hostname()}",
        body=body,
        importance="High",
    )


def contact_status() -> dict[str, Any]:
    email = get_contact_email()
    return {
        "contact_email": email or "",
        "configured": bool(email),
        "hostname": panel_hostname(),
        "events": {
            key: is_event_enabled(key)
            for key in (
                EVENT_ACCOUNT_CREATION,
                EVENT_ACCOUNT_SUSPEND,
                EVENT_ACCOUNT_TERMINATION,
                EVENT_PASSWORD_RESET,
                EVENT_BACKUP_FAILURE,
            )
        },
        "checked_at": timezone.now().isoformat(),
    }
