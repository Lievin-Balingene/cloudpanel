"""Services WordPress : install wp-cli, MySQL, PHP-FPM, suppression."""
from __future__ import annotations

import base64
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


def _clear_welcome_index(docroot: Path, *, force: bool = False) -> bool:
    """
    Retire index.html / index.htm qui masquent WordPress.

    Nginx/OLS listent index.html AVANT index.php → la page « Site prêt »
    continue de s'afficher tant qu'elle existe, même après wp core install.
    """
    removed = False
    for name in ("index.html", "index.htm", "index.HTML", "index.HTM"):
        path = docroot / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        is_welcome = any(
            marker in text
            for marker in (
                "Site prêt",
                "Site Ready",
                "V-zone",
                "cPanel",
                "Document root",
                "prêt à recevoir du contenu",
                "ready to receive content",
            )
        )
        # Si WP (ou autre PHP) est déjà là, toujours enlever le HTML d'accueil
        has_wp = (docroot / "index.php").is_file() or (docroot / "wp-config.php").is_file()
        if force or is_welcome or has_wp:
            try:
                path.unlink(missing_ok=True)
                removed = True
                logger.info("Removed conflicting %s in %s", name, docroot)
            except OSError:
                logger.exception("Cannot remove %s in %s", name, docroot)
    return removed


def repair_wordpress_frontends(user: User | None = None) -> int:
    """Corrige les sites WP actifs encore masqués par index.html (Site prêt)."""
    qs = WordPressSite.objects.filter(status=WordPressSite.Status.ACTIVE)
    if user is not None and user.role != User.Role.ADMINISTRATOR:
        qs = sites_qs(user).filter(status=WordPressSite.Status.ACTIVE)
    fixed = 0
    for site in qs.iterator():
        root = Path(site.document_root) if site.document_root else None
        if root is None or not root.is_dir():
            continue
        if not (root / "index.php").is_file() and not (root / "wp-config.php").is_file():
            continue
        if _clear_welcome_index(root, force=True):
            fixed += 1
    return fixed


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
            # Toujours retirer la page « Site prêt » (sinon elle prime sur index.php)
            _clear_welcome_index(docroot, force=True)

            _run_wp(
                ["core", "download", f"--locale={locale}", "--force"],
                path=docroot,
                php_version=site.php_version,
                timeout=420,
            )
            # wp download peut laisser / réécrire des stubs — purge HTML d'accueil à nouveau
            _clear_welcome_index(docroot, force=True)

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
            _clear_welcome_index(docroot, force=True)
            _fix_ownership(docroot, owner.username)
        else:
            _mock_install(docroot, title=title, site_url=site_url)
            _clear_welcome_index(docroot, force=True)

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


def resolve_site(
    user: User,
    *,
    site_id: int | None = None,
    domain_name: str = "",
) -> WordPressSite | None:
    qs = sites_qs(user)
    if site_id:
        return qs.filter(pk=site_id).first()
    name = (domain_name or "").strip().lower()
    if name:
        return qs.filter(domain__name__iexact=name).first()
    if qs.count() == 1:
        return qs.first()
    return None


def _wp_out(proc: subprocess.CompletedProcess) -> str:
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def _wp_eval(site: WordPressSite, php_code: str, *, timeout: int = 120) -> str:
    docroot = Path(site.document_root)
    proc = _run_wp(
        ["eval", php_code, "--skip-plugins"],
        path=docroot,
        php_version=site.php_version or "",
        timeout=timeout,
    )
    return _wp_out(proc)


_NATURE_CSS = """
/* V-zone Nature Design */
:root {
  --vz-forest: #1f4d2e;
  --vz-moss: #2f6b45;
  --vz-leaf: #4caf70;
  --vz-sand: #f4efe6;
  --vz-bark: #5c4033;
  --vz-mist: #e8f0ea;
  --vz-ink: #1a2e22;
}
html { scroll-behavior: smooth; }
body {
  background: var(--vz-sand) !important;
  color: var(--vz-ink) !important;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif !important;
  line-height: 1.65;
}
h1, h2, h3, .site-title, .entry-title {
  font-family: Georgia, "Times New Roman", serif !important;
  color: var(--vz-forest) !important;
  letter-spacing: -0.02em;
  font-weight: 600;
}
a { color: var(--vz-moss); }
a:hover { color: var(--vz-leaf); }
.site-header, header.site-header, .main-header-bar,
.ast-primary-header-bar, #masthead {
  background: rgba(255,255,255,0.92) !important;
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(31,77,46,0.08) !important;
  box-shadow: 0 1px 0 rgba(31,77,46,0.04);
}
.main-navigation a, .ast-builder-menu a, .menu-link {
  font-weight: 500 !important;
  color: var(--vz-forest) !important;
  letter-spacing: 0.02em;
}
.vz-hero {
  position: relative;
  min-height: clamp(420px, 72vh, 720px);
  display: flex;
  align-items: flex-end;
  padding: clamp(2rem, 6vw, 5rem);
  border-radius: 0 0 2rem 2rem;
  overflow: hidden;
  background:
    linear-gradient(180deg, rgba(15,40,24,0.15) 0%, rgba(15,40,24,0.78) 100%),
    url("https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=1800&q=80")
    center/cover no-repeat;
  color: #fff;
  margin: 0 0 2.5rem;
}
.vz-hero__inner { max-width: 720px; }
.vz-hero__eyebrow {
  display: inline-block;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  opacity: 0.9;
  margin-bottom: 0.75rem;
}
.vz-hero h1 {
  color: #fff !important;
  font-size: clamp(2.2rem, 5vw, 3.6rem);
  line-height: 1.1;
  margin: 0 0 1rem;
  text-shadow: 0 2px 24px rgba(0,0,0,0.25);
}
.vz-hero p {
  font-size: clamp(1.05rem, 2vw, 1.25rem);
  opacity: 0.95;
  max-width: 36em;
  margin: 0 0 1.5rem;
}
.vz-btn {
  display: inline-block;
  background: var(--vz-leaf);
  color: #fff !important;
  padding: 0.85rem 1.5rem;
  border-radius: 999px;
  text-decoration: none !important;
  font-weight: 600;
  box-shadow: 0 10px 30px rgba(47,107,69,0.35);
  transition: transform .2s ease, background .2s ease;
}
.vz-btn:hover { background: #3d9a5c; transform: translateY(-2px); color: #fff !important; }
.vz-btn--ghost {
  background: transparent;
  border: 1.5px solid rgba(255,255,255,0.7);
  box-shadow: none;
  margin-left: 0.75rem;
}
.vz-section {
  max-width: 1100px;
  margin: 0 auto 3rem;
  padding: 0 1.25rem;
}
.vz-section h2 {
  font-size: clamp(1.6rem, 3vw, 2.2rem);
  margin-bottom: 0.5rem;
}
.vz-lead { color: #3d5346; font-size: 1.1rem; margin-bottom: 1.75rem; }
.vz-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1.25rem;
}
.vz-card {
  background: #fff;
  border-radius: 1.25rem;
  padding: 1.5rem;
  border: 1px solid rgba(31,77,46,0.08);
  box-shadow: 0 12px 40px rgba(26,46,34,0.06);
  transition: transform .2s ease, box-shadow .2s ease;
}
.vz-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 18px 48px rgba(26,46,34,0.1);
}
.vz-card__icon {
  width: 2.5rem; height: 2.5rem;
  border-radius: 0.75rem;
  background: var(--vz-mist);
  display: grid; place-items: center;
  margin-bottom: 1rem;
  color: var(--vz-moss);
  font-size: 1.2rem;
}
.vz-card h3 { margin: 0 0 0.5rem; font-size: 1.15rem; }
.vz-card p { margin: 0; color: #4a5d52; font-size: 0.95rem; }
.vz-cta {
  background: linear-gradient(135deg, var(--vz-forest), var(--vz-moss));
  color: #fff;
  border-radius: 1.5rem;
  padding: clamp(2rem, 5vw, 3rem);
  text-align: center;
  margin: 3rem auto;
  max-width: 1100px;
}
.vz-cta h2 { color: #fff !important; margin-top: 0; }
.vz-cta p { opacity: 0.92; max-width: 36em; margin: 0.75rem auto 1.5rem; }
.site-footer, footer, .ast-footer-overlay {
  background: var(--vz-forest) !important;
  color: rgba(255,255,255,0.85) !important;
}
.site-footer a, footer a { color: #b8e0c4 !important; }
.entry-content { font-size: 1.05rem; }
.wp-block-post-title a, .entry-title a { text-decoration: none; }
@media (max-width: 640px) {
  .vz-btn--ghost { display: block; margin: 0.75rem 0 0; text-align: center; }
}
"""


_HOME_HTML = """
<!-- wp:html -->
<div class="vz-hero">
  <div class="vz-hero__inner">
    <span class="vz-hero__eyebrow">Nature &amp; biodiversite</span>
    <h1>Echappee Verte</h1>
    <p>Explorez forets, faune et paysages — un espace immersif pour ressentir, comprendre et proteger le vivant.</p>
    <p>
      <a class="vz-btn" href="#decouvrir">Decouvrir</a>
      <a class="vz-btn vz-btn--ghost" href="/category/nature/">Lire les articles</a>
    </p>
  </div>
</div>
<div class="vz-section" id="decouvrir">
  <h2>Notre mission</h2>
  <p class="vz-lead">Sensibiliser a la beaute du monde naturel et transmettre des gestes concrets pour la biodiversite.</p>
  <div class="vz-grid">
    <article class="vz-card">
      <div class="vz-card__icon">F</div>
      <h3>Forets &amp; paysages</h3>
      <p>Reportages immersifs sur les grands espaces, sentiers et canopees.</p>
    </article>
    <article class="vz-card">
      <div class="vz-card__icon">B</div>
      <h3>Faune &amp; flore</h3>
      <p>Portraits d'especes, cycles des saisons et interactions du vivant.</p>
    </article>
    <article class="vz-card">
      <div class="vz-card__icon">A</div>
      <h3>Agir localement</h3>
      <p>Idees simples pour jardins, balcons et collectivites.</p>
    </article>
  </div>
</div>
<div class="vz-cta">
  <h2>Rejoignez l'echappee</h2>
  <p>Des recits, des images et des pistes concretes pour reconnecter les regards a la nature.</p>
  <a class="vz-btn" href="/a-propos/">En savoir plus</a>
</div>
<!-- /wp:html -->
"""

_ABOUT_HTML = """
<!-- wp:html -->
<div class="vz-section" style="padding-top:2rem">
  <h2>A propos d'Echappee Verte</h2>
  <p class="vz-lead">Une invitation a ralentir, observer et celebrer le vivant — temoignages, photographie et vulgarisation accessible.</p>
  <div class="vz-grid">
    <article class="vz-card"><h3>Emerveiller</h3><p>Des images et recits qui rappellent pourquoi la nature nous touche.</p></article>
    <article class="vz-card"><h3>Comprendre</h3><p>Des cles claires sur les ecosystemes, sans jargon inutile.</p></article>
    <article class="vz-card"><h3>Proteger</h3><p>Des actions concretes, locales et realistes pour chacun.</p></article>
  </div>
</div>
<!-- /wp:html -->
"""

_GALLERY_HTML = """
<!-- wp:html -->
<div class="vz-section" style="padding-top:2rem">
  <h2>Galerie nature</h2>
  <p class="vz-lead">Une selection visuelle pour s'impregner des textures, lumieres et silences du dehors.</p>
  <div class="vz-grid">
    <div class="vz-card" style="padding:0;overflow:hidden">
      <img src="https://images.unsplash.com/photo-1511497584788-876760111969?auto=format&amp;fit=crop&amp;w=900&amp;q=80" alt="Foret brumeuse" style="width:100%;height:220px;object-fit:cover;display:block" />
      <div style="padding:1rem"><h3>Brumes matinales</h3><p>Quand la canopee s'eveille.</p></div>
    </div>
    <div class="vz-card" style="padding:0;overflow:hidden">
      <img src="https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&amp;fit=crop&amp;w=900&amp;q=80" alt="Montagnes" style="width:100%;height:220px;object-fit:cover;display:block" />
      <div style="padding:1rem"><h3>Cretes &amp; horizons</h3><p>L'appel des grands espaces.</p></div>
    </div>
    <div class="vz-card" style="padding:0;overflow:hidden">
      <img src="https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?auto=format&amp;fit=crop&amp;w=900&amp;q=80" alt="Vallee" style="width:100%;height:220px;object-fit:cover;display:block" />
      <div style="padding:1rem"><h3>Vallees vertes</h3><p>La mosaique des habitats.</p></div>
    </div>
  </div>
</div>
<!-- /wp:html -->
"""

_CONTACT_HTML = """
<!-- wp:html -->
<div class="vz-section" style="padding-top:2rem">
  <h2>Contact</h2>
  <p class="vz-lead">Une idee d'article, un partenariat local ou simplement un message ?</p>
  <div class="vz-card" style="max-width:520px">
    <p><strong>Email</strong><br>contact@nature.local</p>
    <p style="margin:0;color:#4a5d52">Remplacez cette adresse dans l'admin WordPress (page Contact).</p>
  </div>
</div>
<!-- /wp:html -->
"""

_POSTS = (
    (
        "Les plus belles forets a explorer",
        "Des sentiers sous canopee aux forets anciennes : pistes pour une echappee respectueuse du vivant.",
    ),
    (
        "Proteger la biodiversite pres de chez soi",
        "Haies, mares, plantes locales : gestes simples qui font une vraie difference pour les especes.",
    ),
    (
        "Faune et flore : observer sans deranger",
        "Conseils de terrain pour photographier et decouvrir la nature en douceur.",
    ),
)


def beautify_wordpress_site(
    site: WordPressSite,
    *,
    style: str = "nature",
    theme: str = "astra",
) -> dict:
    """Applique un design immersif (theme + pages + CSS + menu + articles)."""
    del style
    if site.status != WordPressSite.Status.ACTIVE:
        raise VZoneAPIException(
            detail=f"Site WordPress non actif (status={site.status}).",
            code="wp_not_active",
            status_code=400,
        )
    docroot = Path(site.document_root or "")
    if not docroot.is_dir() or not (docroot / "wp-config.php").is_file():
        raise VZoneAPIException(
            detail="Installation WordPress introuvable sur le disque.",
            code="wp_missing",
            status_code=404,
        )

    if not should_execute():
        css_path = docroot / "wp-content" / "vz-nature.css"
        css_path.parent.mkdir(parents=True, exist_ok=True)
        css_path.write_text(_NATURE_CSS, encoding="utf-8")
        return {
            "mode": "mock",
            "site_id": site.pk,
            "domain": site.domain.name,
            "note": "wp-cli indisponible — CSS depose uniquement.",
            "css": str(css_path),
        }

    php_ver = site.php_version or ""
    theme_slug = (theme or "astra").strip().lower() or "astra"
    if not re.fullmatch(r"[a-z0-9-]{2,40}", theme_slug):
        theme_slug = "astra"

    steps: list[str] = []

    try:
        _run_wp(
            ["theme", "install", theme_slug, "--activate", "--force"],
            path=docroot,
            php_version=php_ver,
            timeout=300,
        )
        steps.append(f"theme:{theme_slug}")
    except VZoneAPIException:
        _run_wp(
            ["theme", "activate", "twentytwentyfour"],
            path=docroot,
            php_version=php_ver,
        )
        theme_slug = "twentytwentyfour"
        steps.append("theme:twentytwentyfour")

    title = (site.title or "Echappee Verte").strip() or "Echappee Verte"
    tagline = "Nature, biodiversite & paysages"
    _run_wp(["option", "update", "blogname", title], path=docroot, php_version=php_ver)
    _run_wp(["option", "update", "blogdescription", tagline], path=docroot, php_version=php_ver)
    _run_wp(["option", "update", "timezone_string", "Europe/Paris"], path=docroot, php_version=php_ver)
    steps.append("identity")

    css_b64 = base64.b64encode(_NATURE_CSS.encode("utf-8")).decode("ascii")
    css_php = (
        f"$css = base64_decode('{css_b64}');\n"
        "if (function_exists('wp_update_custom_css_post')) {\n"
        "  $r = wp_update_custom_css_post($css);\n"
        "  if (is_wp_error($r)) { echo 'css_err:'.$r->get_error_message(); }\n"
        "  else { echo 'css_ok:'.$r->ID; }\n"
        "} else { echo 'css_unavailable'; }\n"
    )
    steps.append("css:" + (_wp_eval(site, css_php) or "done")[:80])

    def _upsert_page(slug: str, page_title: str, content: str) -> int:
        b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        php = (
            f"$slug = {slug!r};\n"
            f"$title = {page_title!r};\n"
            f"$content = base64_decode('{b64}');\n"
            "$existing = get_page_by_path($slug);\n"
            "if ($existing) {\n"
            "  wp_update_post(array('ID'=>$existing->ID,'post_title'=>$title,"
            "'post_content'=>$content,'post_status'=>'publish'));\n"
            "  echo (int)$existing->ID;\n"
            "} else {\n"
            "  $id = wp_insert_post(array(\n"
            "    'post_title'=>$title,'post_name'=>$slug,'post_content'=>$content,\n"
            "    'post_status'=>'publish','post_type'=>'page','post_author'=>1\n"
            "  ));\n"
            "  echo (int)$id;\n"
            "}\n"
        )
        out = _wp_eval(site, php).strip()
        m = re.search(r"(\d+)", out or "")
        return int(m.group(1)) if m else 0

    home_id = _upsert_page("accueil", "Accueil", _HOME_HTML)
    about_id = _upsert_page("a-propos", "A propos", _ABOUT_HTML)
    gallery_id = _upsert_page("galerie", "Galerie", _GALLERY_HTML)
    contact_id = _upsert_page("contact", "Contact", _CONTACT_HTML)
    steps.append(f"pages:{home_id},{about_id},{gallery_id},{contact_id}")

    if home_id:
        _run_wp(["option", "update", "show_on_front", "page"], path=docroot, php_version=php_ver)
        _run_wp(["option", "update", "page_on_front", str(home_id)], path=docroot, php_version=php_ver)
        steps.append("front_page")

    _wp_eval(
        site,
        "$term = term_exists('nature', 'category');\n"
        "if (!$term) { wp_insert_term('Nature', 'category', array('slug'=>'nature')); }\n"
        "echo 'cat_ok';\n",
    )
    posts_created = 0
    for ptitle, excerpt in _POSTS:
        body = (
            f"<p>{excerpt}</p>"
            "<p>La nature nous rappelle que chaque detail participe a un equilibre fragile. "
            "Prenez le temps d observer et de transmettre.</p>"
        )
        b64 = base64.b64encode(body.encode("utf-8")).decode("ascii")
        php = (
            f"$title = {ptitle!r};\n"
            f"$excerpt = {excerpt!r};\n"
            f"$content = base64_decode('{b64}');\n"
            "global $wpdb;\n"
            "$id = (int)$wpdb->get_var($wpdb->prepare(\n"
            "  \"SELECT ID FROM {$wpdb->posts} WHERE post_title=%s AND post_type='post' "
            "AND post_status='publish' LIMIT 1\", $title));\n"
            "if ($id) { echo $id; }\n"
            "else {\n"
            "  $nid = wp_insert_post(array(\n"
            "    'post_title'=>$title,'post_content'=>$content,'post_excerpt'=>$excerpt,\n"
            "    'post_status'=>'publish','post_type'=>'post','post_author'=>1\n"
            "  ));\n"
            "  if ($nid && !is_wp_error($nid)) {\n"
            "    $cat = get_cat_ID('Nature');\n"
            "    if ($cat) { wp_set_post_categories($nid, array($cat)); }\n"
            "    echo (int)$nid;\n"
            "  } else { echo 0; }\n"
            "}\n"
        )
        out = (_wp_eval(site, php) or "").strip()
        if out.isdigit() and int(out) > 0:
            posts_created += 1
    steps.append(f"posts:{posts_created}")

    menu_php = (
        f"$menu_name = 'Principal';\n"
        "$menu = wp_get_nav_menu_object($menu_name);\n"
        "if (!$menu) { $menu_id = wp_create_nav_menu($menu_name); }\n"
        "else {\n"
        "  $menu_id = (int)$menu->term_id;\n"
        "  $items = wp_get_nav_menu_items($menu_id);\n"
        "  if ($items) { foreach ($items as $item) { wp_delete_post($item->ID, true); } }\n"
        "}\n"
        f"$pages = array({int(home_id)}, {int(about_id)}, {int(gallery_id)}, {int(contact_id)});\n"
        "$pos = 1;\n"
        "foreach ($pages as $pid) {\n"
        "  if (!$pid) continue;\n"
        "  wp_update_nav_menu_item($menu_id, 0, array(\n"
        "    'menu-item-object-id' => $pid,\n"
        "    'menu-item-object' => 'page',\n"
        "    'menu-item-type' => 'post_type',\n"
        "    'menu-item-status' => 'publish',\n"
        "    'menu-item-position' => $pos++,\n"
        "  ));\n"
        "}\n"
        "$locations = get_theme_mod('nav_menu_locations');\n"
        "if (!is_array($locations)) { $locations = array(); }\n"
        "foreach (array('primary','menu-1','main','primary-menu','header-menu') as $loc) {\n"
        "  $locations[$loc] = $menu_id;\n"
        "}\n"
        "set_theme_mod('nav_menu_locations', $locations);\n"
        "echo 'menu:'.$menu_id;\n"
    )
    steps.append((_wp_eval(site, menu_php) or "menu")[:40])

    try:
        _run_wp(
            ["rewrite", "structure", "/%postname%/", "--hard"],
            path=docroot,
            php_version=php_ver,
        )
    except VZoneAPIException:
        pass
    try:
        username = (site.owner.username or site.owner.system_username or "").strip()
        if username:
            _fix_ownership(docroot, username)
    except Exception:  # noqa: BLE001
        logger.debug("chown after beautify skip", exc_info=True)

    site.title = title
    site.save(update_fields=["title", "updated_at"])

    return {
        "site_id": site.pk,
        "domain": site.domain.name,
        "site_url": site.site_url or _site_url(site.domain),
        "theme": theme_slug,
        "style": "nature",
        "pages": {
            "accueil": home_id,
            "a_propos": about_id,
            "galerie": gallery_id,
            "contact": contact_id,
        },
        "posts_created": posts_created,
        "steps": steps,
        "message": (
            f"Design nature applique sur {site.domain.name} "
            f"(theme {theme_slug}, pages, articles, menu, CSS)."
        ),
    }
