"""Services WordPress : install wp-cli, MySQL, PHP-FPM, suppression."""
from __future__ import annotations

import logging
import os
import re
import secrets
import shutil
import string
import subprocess
from pathlib import Path

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.databases.models import DatabaseEngine
from apps.databases.services import (
    create_database,
    create_database_user,
    delete_database,
    delete_database_user,
    grant_privilege,
)
from apps.domains.models import Domain
from apps.files.services import personal_home
from apps.php.models import PhpSelector, PhpVersion
from apps.php.services import (
    create_selector,
    ensure_default_versions,
    discover_system_versions,
)
from apps.wordpress.models import WordPressSite

logger = logging.getLogger(__name__)


def sites_qs(user: User) -> QuerySet[WordPressSite]:
    qs = WordPressSite.objects.select_related(
        "owner", "domain", "database", "db_user", "php_selector"
    )
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def overview_for(user: User) -> dict:
    qs = sites_qs(user)
    return {
        "sites": qs.count(),
        "active": qs.filter(status=WordPressSite.Status.ACTIVE).count(),
        "error": qs.filter(status=WordPressSite.Status.ERROR).count(),
        "provisioning": qs.filter(status=WordPressSite.Status.PROVISIONING).count(),
        "wp_cli": bool(_wp_cli_bin()),
        "provision_mode": provision_mode(),
    }


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_WORDPRESS_PROVISION_MODE", "auto").lower()
    return mode if mode in {"auto", "live", "mock"} else "auto"


def should_execute() -> bool:
    mode = provision_mode()
    if mode == "mock":
        return False
    if mode == "live":
        return True
    return bool(_wp_cli_bin())


def _wp_cli_bin() -> str | None:
    configured = getattr(settings, "VZONE_WP_CLI", "") or ""
    candidates = [
        configured,
        "/usr/local/bin/wp",
        shutil.which("wp") or "",
    ]
    for c in candidates:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


def _php_bin(version: str = "") -> str:
    if version:
        for candidate in (f"/usr/bin/php{version}", shutil.which(f"php{version}") or ""):
            if candidate and Path(candidate).is_file():
                return candidate
    for candidate in (
        shutil.which("php") or "",
        "/usr/bin/php",
        "/usr/bin/php8.3",
        "/usr/bin/php8.2",
        "/usr/bin/php8.1",
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return "php"


def _refresh_routing() -> None:
    try:
        from apps.domains.services import refresh_web_routing

        refresh_web_routing()
    except Exception:  # noqa: BLE001
        logger.debug("refresh_web_routing skip", exc_info=True)


def _gen_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _relative_docroot(owner: User, domain: Domain) -> tuple[str, Path]:
    home = personal_home(owner)
    raw = (domain.document_root or "").strip()
    if not raw:
        raise VZoneAPIException(
            detail="Document root du domaine manquant.",
            code="no_docroot",
            status_code=400,
        )
    target = Path(raw).resolve()
    try:
        rel = str(target.relative_to(home.resolve())).replace("\\", "/")
    except ValueError as exc:
        raise VZoneAPIException(
            detail="Document root hors du home du compte.",
            code="path_forbidden",
            status_code=403,
        ) from exc
    if ".." in Path(rel).parts:
        raise VZoneAPIException(detail="Chemin invalide.", code="invalid_path", status_code=400)
    target.mkdir(parents=True, exist_ok=True)
    return rel, target


def _site_url(domain: Domain) -> str:
    has_ssl = False
    try:
        from apps.domains.ssl_services import has_active_cert_files

        has_ssl = has_active_cert_files(domain.name)
    except Exception:  # noqa: BLE001
        pass
    scheme = "https" if has_ssl else "http"
    return f"{scheme}://{domain.name}"


def _run_wp(
    args: list[str],
    *,
    path: Path,
    php_version: str = "",
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    wp = _wp_cli_bin()
    if not wp:
        raise VZoneAPIException(
            detail=(
                "wp-cli introuvable. Exécutez: "
                "sudo bash /opt/vzone-src/scripts/install-wp-cli.sh"
            ),
            code="wp_cli_missing",
            status_code=503,
        )
    php = _php_bin(php_version)
    cmd = [php, wp, f"--path={path}", "--allow-root", *args]
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=timeout,
            env={**os.environ, "HOME": str(path)},
        )
    except subprocess.TimeoutExpired as exc:
        raise VZoneAPIException(
            detail="Timeout commande WordPress (wp-cli).",
            code="wp_timeout",
            status_code=504,
        ) from exc
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        stderr = getattr(exc, "stderr", None) or str(exc)
        raise VZoneAPIException(
            detail=f"Échec wp-cli: {str(stderr)[-800:]}",
            code="wp_cmd_failed",
            status_code=502,
            extra={"cmd": cmd},
        ) from exc


def _fix_ownership(path: Path, username: str) -> None:
    """Propriétaire = compte, groupe www-data pour écriture PHP-FPM."""
    try:
        import grp
        import pwd

        uid = pwd.getpwnam(username).pw_uid
        try:
            gid = grp.getgrnam("www-data").gr_gid
        except KeyError:
            gid = pwd.getpwnam(username).pw_gid
    except (ImportError, KeyError):
        return
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            os.chown(dirpath, uid, gid)
            try:
                os.chmod(dirpath, 0o775)
            except OSError:
                pass
            for name in filenames:
                fp = Path(dirpath) / name
                os.chown(fp, uid, gid)
                try:
                    os.chmod(fp, 0o664)
                except OSError:
                    pass
    except (PermissionError, OSError) as exc:
        logger.warning("chown WordPress skip %s: %s", path, exc)


def _ensure_php_selector(owner: User, domain: Domain, rel: str) -> PhpSelector:
    ensure_default_versions()
    if provision_mode() != "mock":
        try:
            discover_system_versions()
        except Exception:  # noqa: BLE001
            logger.debug("discover php skip", exc_info=True)

    existing = (
        PhpSelector.objects.filter(owner=owner, relative_path=rel, is_active=True)
        .select_related("php_version")
        .first()
    )
    if existing:
        if existing.domain_name != domain.name.lower():
            existing.domain_name = domain.name.lower()
            existing.save(update_fields=["domain_name", "updated_at"])
            _refresh_routing()
        return existing

    by_domain = (
        PhpSelector.objects.filter(owner=owner, domain_name=domain.name.lower(), is_active=True)
        .select_related("php_version")
        .first()
    )
    if by_domain:
        return by_domain

    version = (
        PhpVersion.objects.filter(is_default=True, is_available=True).first()
        or PhpVersion.objects.filter(is_available=True).order_by("-version").first()
    )
    if version is None:
        raise VZoneAPIException(
            detail="Aucune version PHP disponible. Installez php-fpm.",
            code="php_missing",
            status_code=503,
        )
    return create_selector(
        owner=owner,
        php_version_id=version.pk,
        relative_path=rel,
        domain_name=domain.name,
        notes="WordPress auto",
    )


def _mock_install(docroot: Path, *, title: str, site_url: str) -> None:
    docroot.mkdir(parents=True, exist_ok=True)
    (docroot / "index.php").write_text(
        "<?php\n// WordPress mock — V-zone Panel\necho 'WordPress OK';\n",
        encoding="utf-8",
    )
    (docroot / "wp-config.php").write_text(
        f"<?php\n// mock config for {title} @ {site_url}\n",
        encoding="utf-8",
    )
    (docroot / "wp-admin").mkdir(exist_ok=True)
    (docroot / "wp-admin" / "index.php").write_text("<?php\n", encoding="utf-8")


def _db_slug(domain_name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", domain_name.lower()).strip("_")
    base = re.sub(r"_+", "_", base)[:18] or "wp"
    if not base[0].isalpha():
        base = f"w{base}"
    return base[:18]


def install_wordpress(
    *,
    owner: User,
    domain_id: int,
    title: str = "Mon site",
    admin_user: str = "admin",
    admin_email: str = "",
    admin_password: str = "",
    locale: str = "fr_FR",
) -> tuple[WordPressSite, str]:
    """Installe WordPress sur un domaine. Retourne (site, mot_de_passe_admin)."""
    domain = Domain.objects.select_related("owner").filter(pk=domain_id).first()
    if domain is None or domain.owner_id != owner.pk:
        raise VZoneAPIException(
            detail="Domaine introuvable pour ce compte.",
            code="domain_not_found",
            status_code=404,
        )
    if WordPressSite.objects.filter(domain_id=domain.pk).exists():
        raise VZoneAPIException(
            detail="WordPress est déjà installé sur ce domaine.",
            code="wp_exists",
            status_code=400,
        )
    try:
        from apps.domains.vhosts import is_panel_hostname

        if is_panel_hostname(domain.name):
            raise VZoneAPIException(
                detail="Impossible d'installer WordPress sur le hostname du panel.",
                code="panel_hostname",
                status_code=400,
            )
    except VZoneAPIException:
        raise
    except Exception:  # noqa: BLE001
        pass

    title = (title or "Mon site").strip()[:200] or "Mon site"
    admin_user = (admin_user or "admin").strip()[:60] or "admin"
    if not re.match(r"^[A-Za-z0-9._-]{3,60}$", admin_user):
        raise VZoneAPIException(
            detail="Identifiant admin invalide (3–60 caractères alphanumériques).",
            code="invalid_admin_user",
            status_code=400,
        )
    email = (admin_email or owner.email or f"{owner.username}@localhost").strip()
    password = (admin_password or "").strip() or _gen_password(20)
    if len(password) < 8:
        raise VZoneAPIException(
            detail="Mot de passe admin trop court (min 8).",
            code="weak_password",
            status_code=400,
        )

    rel, docroot = _relative_docroot(owner, domain)
    site_url = _site_url(domain)

    site = WordPressSite.objects.create(
        owner=owner,
        domain=domain,
        title=title,
        admin_user=admin_user,
        admin_email=email,
        document_root=str(docroot),
        site_url=site_url,
        admin_url=f"{site_url.rstrip('/')}/wp-admin/",
        status=WordPressSite.Status.PROVISIONING,
    )

    slug = _db_slug(domain.name)
    db_password = _gen_password(24)
    try:
        db = create_database(
            owner=owner,
            name=f"wp_{slug}"[:40],
            engine=DatabaseEngine.MYSQL,
            notes=f"WordPress {domain.name}",
        )
        db_user = create_database_user(
            owner=owner,
            username=f"wp_{slug}"[:28],
            password=db_password,
            engine=DatabaseEngine.MYSQL,
            notes=f"WordPress {domain.name}",
        )
        grant_privilege(database=db, user=db_user, privileges="ALL")
        site.database = db
        site.db_user = db_user
        site.save(update_fields=["database", "db_user", "updated_at"])

        selector = _ensure_php_selector(owner, domain, rel)
        site.php_selector = selector
        site.php_version = selector.php_version.version
        site.save(update_fields=["php_selector", "php_version", "updated_at"])

        mysql_host = getattr(settings, "VZONE_MYSQL_HOST", "") or "localhost"
        if mysql_host in {"127.0.0.1", "::1"}:
            mysql_host = "localhost"

        if should_execute():
            # Retirer la page d'accueil panel si présente
            welcome = docroot / "index.html"
            if welcome.is_file() and "V-zone" in welcome.read_text(encoding="utf-8", errors="ignore"):
                welcome.unlink(missing_ok=True)

            _run_wp(
                ["core", "download", f"--locale={locale}", "--force"],
                path=docroot,
                php_version=site.php_version,
                timeout=420,
            )
            _run_wp(
                [
                    "config",
                    "create",
                    f"--dbname={db.name}",
                    f"--dbuser={db_user.username}",
                    f"--dbpass={db_password}",
                    f"--dbhost={mysql_host}",
                    "--dbcharset=utf8mb4",
                    "--dbcollate=utf8mb4_unicode_ci",
                    "--skip-check",
                    "--force",
                ],
                path=docroot,
                php_version=site.php_version,
            )
            _run_wp(
                [
                    "core",
                    "install",
                    f"--url={site_url}",
                    f"--title={title}",
                    f"--admin_user={admin_user}",
                    f"--admin_password={password}",
                    f"--admin_email={email}",
                    "--skip-email",
                ],
                path=docroot,
                php_version=site.php_version,
            )
            _run_wp(
                ["rewrite", "structure", "/%postname%/", "--hard"],
                path=docroot,
                php_version=site.php_version,
            )
            _fix_ownership(docroot, owner.username)
        else:
            _mock_install(docroot, title=title, site_url=site_url)

        site.status = WordPressSite.Status.ACTIVE
        site.last_error = ""
        site.updated_at = timezone.now()
        site.save(update_fields=["status", "last_error", "updated_at"])
        _refresh_routing()
        return site, password
    except Exception as exc:
        site.status = WordPressSite.Status.ERROR
        site.last_error = str(getattr(exc, "detail", None) or exc)[:2000]
        site.save(update_fields=["status", "last_error", "updated_at"])
        if isinstance(exc, (VZoneAPIException, QuotaExceeded)):
            raise
        raise VZoneAPIException(
            detail=f"Installation WordPress échouée: {exc}",
            code="wp_install_failed",
            status_code=502,
        ) from exc


def delete_wordpress(
    site: WordPressSite,
    *,
    remove_files: bool = True,
    remove_database: bool = True,
) -> None:
    site.status = WordPressSite.Status.REMOVING
    site.save(update_fields=["status", "updated_at"])

    docroot = Path(site.document_root) if site.document_root else None
    db = site.database
    db_user = site.db_user
    selector = site.php_selector
    domain_name = site.domain.name if site.domain_id else ""

    site.delete()

    if remove_database:
        if db is not None:
            try:
                delete_database(db)
            except Exception:  # noqa: BLE001
                logger.exception("drop WP database failed")
        if db_user is not None:
            try:
                delete_database_user(db_user)
            except Exception:  # noqa: BLE001
                logger.exception("drop WP db user failed")

    if remove_files and docroot and docroot.is_dir():
        # Ne pas supprimer tout le home — seulement le contenu WP du docroot
        for name in (
            "wp-admin",
            "wp-includes",
            "wp-content",
            "wp-config.php",
            "wp-config-sample.php",
            "xmlrpc.php",
            "license.txt",
            "readme.html",
            "wp-*.php",
            "index.php",
            ".htaccess",
        ):
            if "*" in name:
                for p in docroot.glob(name):
                    if p.is_file():
                        p.unlink(missing_ok=True)
            else:
                target = docroot / name
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                elif target.is_file():
                    target.unlink(missing_ok=True)
        # Page d'accueil de secours
        index = docroot / "index.html"
        if not index.exists() and not (docroot / "index.php").exists():
            index.write_text(
                f"<!DOCTYPE html><html><body><h1>{domain_name}</h1>"
                "<p>Site prêt — WordPress désinstallé.</p></body></html>\n",
                encoding="utf-8",
            )

    if selector is not None and (selector.notes or "") == "WordPress auto":
        try:
            from apps.php.services import delete_selector

            delete_selector(selector)
        except Exception:  # noqa: BLE001
            logger.debug("delete php selector skip", exc_info=True)

    _refresh_routing()
