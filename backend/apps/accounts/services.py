"""Services métier comptes : JWT, 2FA, audit de connexion, homes cPanel."""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from pathlib import Path

import pyotp
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, UserSession
from apps.core.exceptions import VZoneAPIException
from apps.core.models import AuditLog

logger = logging.getLogger(__name__)

# Style cPanel : commence par une lettre, alphanumérique / _ / -, 3–32 car.
SYSTEM_USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")
RESERVED_USERNAMES = frozenset(
    {
        "admin",
        "root",
        "vzone",
        "vmail",
        "nobody",
        "www",
        "mail",
        "ftp",
        "mysql",
        "postgres",
    }
)


def normalize_system_username(username: str) -> str:
    return (username or "").strip().lower()


def validate_system_username(username: str) -> str:
    name = normalize_system_username(username)
    if not SYSTEM_USERNAME_RE.match(name):
        raise VZoneAPIException(
            detail=(
                "Nom d'utilisateur invalide (style cPanel) : "
                "3–32 caractères, commencer par une lettre, "
                "uniquement a-z, 0-9, _ ou -."
            ),
            code="invalid_username",
            status_code=400,
        )
    if name in RESERVED_USERNAMES:
        raise VZoneAPIException(
            detail=f"Le nom d'utilisateur « {name} » est réservé.",
            code="reserved_username",
            status_code=400,
        )
    return name


def provision_account_home(user: User) -> Path:
    """
    Crée le home du compte comme cPanel : VZONE_HOME_ROOT/<username>/
    avec public_html, mail, etc., et renseigne system_username / home_directory.
    """
    from apps.files.services import ensure_cpanel_tree, personal_home

    if user.role == User.Role.ADMINISTRATOR:
        sys_name = (user.system_username or "admin").strip().lower() or "admin"
    else:
        sys_name = validate_system_username(user.system_username or user.username)
        if user.username != sys_name:
            if not User.objects.filter(username=sys_name).exclude(pk=user.pk).exists():
                user.username = sys_name

    user.system_username = sys_name

    home = personal_home(user)
    try:
        ensure_cpanel_tree(home)
    except OSError as exc:
        # /home est souvent root:root 755 — fallback via sudo vzone-mkhome
        if getattr(exc, "errno", None) == 13 or "Permission denied" in str(exc):
            from apps.accounts.linux_users import provision_home_via_root

            try:
                provision_home_via_root(sys_name)
                ensure_cpanel_tree(home)
            except Exception as inner:  # noqa: BLE001
                raise VZoneAPIException(
                    detail=(
                        f"Impossible de créer le home {home}: {exc}. "
                        f"Helper root: {inner}. "
                        "Sur le serveur: sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh "
                        "&& sudo bash /opt/vzone-src/scripts/ensure-homes.sh"
                    ),
                    code="home_provision_failed",
                    status_code=500,
                ) from inner
        else:
            raise VZoneAPIException(
                detail=f"Impossible de créer le home {home}: {exc}",
                code="home_provision_failed",
                status_code=500,
            ) from exc

    user.home_directory = str(home)
    user.save(
        update_fields=["username", "system_username", "home_directory", "updated_at"]
    )
    try:
        from apps.accounts.linux_users import ensure_linux_user

        ensure_linux_user(user, home=home)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Provision OS user skip pour %s: %s", user.username, exc)
    logger.info("Home provisionné pour %s → %s", user.username, home)
    return home


def cpanel_welcome_html(hostname: str, *, account: str = "", document_root: str = "") -> str:
    """Page d'accueil style cPanel / LiteSpeed (« Site prêt ») pour domaine / sous-domaine."""
    acct = account or hostname
    doc = document_root.strip() or "public_html"
    display = doc
    for marker in ("/homes/", "/home/"):
        if marker in doc.replace("\\", "/"):
            parts = doc.replace("\\", "/").split(marker, 1)[-1].split("/", 1)
            if len(parts) == 2:
                display = "~/" + parts[1]
            break
    return (
        "<!DOCTYPE html>\n"
        '<html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{hostname} — Site prêt</title>"
        "<style>"
        "body{margin:0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;"
        "background:#0b1220;color:#e8eef7;min-height:100vh;"
        "display:flex;align-items:center;justify-content:center;"
        "background-image:radial-gradient(ellipse at 20% 0%,#1a3a5c 0%,transparent 50%),"
        "radial-gradient(ellipse at 80% 100%,#0f2a22 0%,transparent 45%)}"
        ".box{max-width:28rem;margin:1.5rem;padding:2.25rem 2rem;text-align:center;"
        "background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);"
        "border-radius:16px;backdrop-filter:blur(8px)}"
        ".badge{display:inline-block;margin-bottom:1rem;padding:.4rem .9rem;"
        "border-radius:999px;background:#12b76a;color:#042f1a;font-size:.75rem;"
        "font-weight:700;letter-spacing:.04em;text-transform:uppercase}"
        "h1{margin:0 0 .75rem;font-size:1.45rem;font-weight:650;color:#fff;"
        "word-break:break-word}"
        "p{margin:.55rem 0;color:#9db0c7;line-height:1.55;font-size:.95rem}"
        "code{font-size:.8rem;background:rgba(0,0,0,.35);padding:.12rem .4rem;"
        "border-radius:4px;color:#c5d4e8;word-break:break-all}"
        ".hint{margin-top:1.25rem;padding-top:1rem;border-top:1px solid rgba(255,255,255,.1);"
        "font-size:.82rem;color:#7a8fa8}"
        "</style></head><body><div class=\"box\">"
        '<div class="badge">Site prêt</div>'
        f"<h1>{hostname}</h1>"
        "<p>Votre site web est actif et prêt à recevoir du contenu.</p>"
        f"<p>Compte <code>{acct}</code><br>Document root <code>{display}</code></p>"
        '<p class="hint">Remplacez <code>index.html</code> ou ajoutez <code>index.php</code> '
        "via le File Manager / FTP.</p>"
        "</div></body></html>\n"
    )


def provision_primary_domain_for_account(
    user: User,
    domain_name: str,
    *,
    create_welcome_index: bool = False,
) -> object:
    """
    Crée le domaine principal du compte (cPanel) :
    Domain primary → ~/public_html, zone DNS + A @/www, vhost.
    """
    from apps.domains.models import Domain
    from apps.domains.services import create_domain

    name = (domain_name or "").strip().lower().rstrip(".")
    if not name or "." not in name:
        raise VZoneAPIException(
            detail="Domaine principal invalide (FQDN requis, ex: exemple.com).",
            code="invalid_primary_domain",
            status_code=400,
        )

    existing = Domain.objects.filter(owner=user, domain_type=Domain.DomainType.PRIMARY).first()
    if existing:
        return existing

    domain = create_domain(
        name=name,
        owner=user,
        domain_type=Domain.DomainType.PRIMARY,
        create_dns_zone=True,
        create_welcome_index=create_welcome_index,
    )
    if create_welcome_index:
        try:
            index = Path(domain.document_root) / "index.html"
            if not index.exists():
                index.write_text(
                    cpanel_welcome_html(domain.name, account=user.username),
                    encoding="utf-8",
                )
        except OSError as exc:
            logger.warning("Impossible d'écrire index.html pour %s: %s", domain.name, exc)

    # Sync vhost immédiat (en plus de on_commit) pour que le site réponde tout de suite
    try:
        from apps.domains.vhosts import sync_domain_vhost

        sync_domain_vhost(domain)
    except Exception:  # noqa: BLE001
        logger.exception("Sync vhost primary échoué pour %s", domain.name)

    return domain


def delete_account(user: User) -> None:
    """Supprime le compte et son home (sauf le home admin partagé)."""
    import shutil

    from django.conf import settings

    from apps.files.services import personal_home

    home_path: Path | None = None
    if user.role != User.Role.ADMINISTRATOR:
        try:
            home_path = personal_home(user)
        except Exception:  # noqa: BLE001
            home_path = None

    username = user.username
    user.delete()

    if home_path is not None and home_path.exists():
        root = Path(settings.VZONE_HOME_ROOT).resolve()
        try:
            resolved = home_path.resolve()
            if resolved != root and root in resolved.parents:
                shutil.rmtree(resolved, ignore_errors=True)
                logger.info("Home supprimé pour %s → %s", username, resolved)
        except OSError as exc:
            logger.warning("Échec suppression home %s: %s", home_path, exc)


def issue_tokens(user: User, request=None) -> dict:  # type: ignore[no-untyped-def]
    """Émet access + refresh JWT et enregistre la session."""
    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    jti = str(refresh["jti"])
    expires_at = timezone.now() + timedelta(
        seconds=int(refresh.access_token.lifetime.total_seconds())
    )

    ip = None
    ua = ""
    if request is not None:
        ip = _client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")[:512]
        user.last_login_ip = ip
        user.save(update_fields=["last_login_ip", "last_login"])

    UserSession.objects.create(
        user=user,
        jti=jti,
        user_agent=ua,
        ip_address=ip,
        expires_at=timezone.now() + refresh.lifetime,
    )

    AuditLog.objects.create(
        actor=user,
        action=AuditLog.Action.LOGIN,
        resource_type="user",
        resource_id=str(user.pk),
        message="Connexion réussie",
        ip_address=ip,
        user_agent=ua,
        request_id=getattr(request, "request_id", ""),
    )

    return {
        "access": str(access),
        "refresh": str(refresh),
        "expires_at": expires_at.isoformat(),
        "must_change_password": user.must_change_password,
    }


def revoke_refresh_token(token_str: str, user: User | None = None) -> None:
    token = RefreshToken(token_str)
    jti = str(token["jti"])
    token.blacklist()
    UserSession.objects.filter(jti=jti).update(is_revoked=True)
    if user is not None:
        AuditLog.objects.create(
            actor=user,
            action=AuditLog.Action.LOGOUT,
            resource_type="user",
            resource_id=str(user.pk),
            message="Déconnexion",
        )


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def _totp_plain(user: User) -> str:
    """Déchiffre le secret TOTP (compat clair historique)."""
    raw = user.two_factor_secret or ""
    if not raw:
        return ""
    if raw.startswith("gAAAA"):
        from apps.databases.crypto import decrypt_secret

        return decrypt_secret(raw) or ""
    return raw


def _store_totp_secret(user: User, plain: str) -> None:
    from apps.databases.crypto import encrypt_secret

    user.two_factor_secret = encrypt_secret(plain) if plain else ""


def verify_totp(user: User, otp: str) -> bool:
    secret = _totp_plain(user)
    if not secret:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(otp, valid_window=1)


def provisioning_uri(user: User) -> str:
    secret = _totp_plain(user)
    if not secret:
        secret = generate_totp_secret()
        _store_totp_secret(user, secret)
        user.save(update_fields=["two_factor_secret"])
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=user.email, issuer_name="V-zone Panel")


def _client_ip(request) -> str | None:  # type: ignore[no-untyped-def]
    from apps.security.services import client_ip

    return client_ip(request)
