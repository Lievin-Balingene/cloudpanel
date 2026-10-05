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
from typing import Any

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
    raw = (domain_name or "").lower()
    base = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    base = re.sub(r"_+", "_", base)[:18]
    if not base:
        base = "wp"
    if not base[0:1].isalpha():
        base = f"w{base}"
    return (base or "wp")[:18]


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


def _vz_pages_dir(docroot: Path) -> Path:
    d = docroot / ".vz-pages"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_vz_page_html(docroot: Path, slug: str, html: str) -> Path:
    path = _vz_pages_dir(docroot) / f"{slug}.html"
    path.write_text(html, encoding="utf-8")
    return path


def _wp_eval(site: WordPressSite, php_code: str, *, timeout: int = 180) -> str:
    """Exécute du PHP via wp eval-file (chemin relatif au docroot)."""
    docroot = Path(site.document_root).resolve()
    if not docroot.is_dir():
        raise VZoneAPIException(
            detail="Document root WordPress invalide.",
            code="wp_missing",
            status_code=404,
        )
    code = (php_code or "").strip()
    if not code:
        return ""
    run_path = _vz_pages_dir(docroot) / "_eval.php"
    run_path.write_text("<?php\n" + code + "\n", encoding="utf-8")
    try:
        os.chmod(run_path, 0o640)
    except OSError:
        pass
    rel = run_path.relative_to(docroot).as_posix()
    proc = _run_wp(
        ["eval-file", rel],
        path=docroot,
        php_version=site.php_version or "",
        timeout=timeout,
    )
    return _wp_out(proc)


def _wp_page_id_by_slug(docroot: Path, slug: str, *, php_ver: str = "") -> int:
    try:
        proc = _run_wp(
            [
                "post",
                "list",
                "--post_type=page",
                f"--name={slug}",
                "--field=ID",
                "--format=ids",
            ],
            path=docroot,
            php_version=php_ver,
        )
        out = (proc.stdout or "").strip()
        return int(out) if out.isdigit() else 0
    except VZoneAPIException:
        return 0


def _upsert_page_from_file(site: WordPressSite, slug: str, title: str, html: str) -> int:
    """Crée/met à jour une page WP depuis un fichier HTML dans .vz-pages/."""
    docroot = Path(site.document_root).resolve()
    _write_vz_page_html(docroot, slug, html)
    php = (
        f"$slug = {slug!r};\n"
        f"$title = {title!r};\n"
        f"$html = file_get_contents({repr(str(docroot / '.vz-pages' / f'{slug}.html'))});\n"
        "if ($html === false) { echo '0'; return; }\n"
        "$page = get_page_by_path($slug, OBJECT, 'page');\n"
        "if (!$page) { $page = get_page_by_path($slug); }\n"
        "if ($page) {\n"
        "  wp_update_post(array(\n"
        "    'ID' => $page->ID, 'post_title' => $title, 'post_name' => $slug,\n"
        "    'post_content' => $html, 'post_status' => 'publish',\n"
        "  ));\n"
        "  echo (int)$page->ID;\n"
        "} else {\n"
        "  $id = wp_insert_post(array(\n"
        "    'post_title' => $title, 'post_name' => $slug, 'post_content' => $html,\n"
        "    'post_status' => 'publish', 'post_type' => 'page', 'post_author' => 1,\n"
        "  ));\n"
        "  echo (int)$id;\n"
        "}\n"
    )
    out = (_wp_eval(site, php) or "").strip()
    m = re.search(r"(\d+)", out or "")
    pid = int(m.group(1)) if m else 0
    if not pid:
        pid = _wp_page_id_by_slug(docroot, slug, php_ver=site.php_version or "")
    return pid


def _upsert_post(site: WordPressSite, slug: str, title: str, excerpt: str, body: str) -> int:
    docroot = Path(site.document_root).resolve()
    php = (
        f"$slug = {slug!r};\n"
        f"$title = {title!r};\n"
        f"$excerpt = {excerpt!r};\n"
        f"$content = {body!r};\n"
        "global $wpdb;\n"
        "$id = (int)$wpdb->get_var($wpdb->prepare(\n"
        "  \"SELECT ID FROM {$wpdb->posts} WHERE post_name=%s AND post_type='post' "
        "AND post_status='publish' LIMIT 1\", $slug));\n"
        "if (!$id) {\n"
        "  $id = (int)$wpdb->get_var($wpdb->prepare(\n"
        "    \"SELECT ID FROM {$wpdb->posts} WHERE post_title=%s AND post_type='post' "
        "AND post_status='publish' LIMIT 1\", $title));\n"
        "}\n"
        "if ($id) {\n"
        "  wp_update_post(array('ID'=>$id,'post_content'=>$content,'post_excerpt'=>$excerpt,"
        "'post_name'=>$slug,'post_status'=>'publish'));\n"
        "  echo $id;\n"
        "} else {\n"
        "  $nid = wp_insert_post(array(\n"
        "    'post_title'=>$title,'post_name'=>$slug,'post_content'=>$content,\n"
        "    'post_excerpt'=>$excerpt,'post_status'=>'publish','post_type'=>'post','post_author'=>1,\n"
        "  ));\n"
        "  if ($nid && !is_wp_error($nid)) {\n"
        "    $cat = get_cat_ID('Nature');\n"
        "    if ($cat) { wp_set_post_categories($nid, array($cat)); }\n"
        "    echo (int)$nid;\n"
        "  } else { echo 0; }\n"
        "}\n"
    )
    try:
        out = (_wp_eval(site, php) or "").strip()
    except VZoneAPIException:
        return 0
    m = re.search(r"(\d+)", out or "")
    return int(m.group(1)) if m else 0


def _flush_wp_rewrites(site: WordPressSite) -> dict[str, Any]:
    """Force permaliens /%postname%/ + .htaccess (LiteSpeed/Apache) pour éviter les 404."""
    docroot = Path(site.document_root).resolve()
    php_ver = site.php_version or ""
    steps: list[str] = []
    for args in (
        ["option", "update", "permalink_structure", "/%postname%/"],
        ["rewrite", "structure", "/%postname%/", "--hard"],
        ["rewrite", "flush", "--hard"],
        ["cache", "flush"],
    ):
        try:
            _run_wp(args, path=docroot, php_version=php_ver)
            steps.append(" ".join(args[:2]))
        except VZoneAPIException as exc:
            steps.append(f"err:{args[0]}:{exc}")

    htaccess = docroot / ".htaccess"
    wp_rules = (
        "# BEGIN WordPress\n"
        "# Les directives entre « BEGIN WordPress » et « END WordPress » sont\n"
        "# générées dynamiquement et ne doivent être modifiées que via les filtres WordPress.\n"
        "# Leur modification peut être écrasée par de prochaines mises à jour.\n"
        "<IfModule mod_rewrite.c>\n"
        "RewriteEngine On\n"
        "RewriteRule .* - [E=HTTP_AUTHORIZATION:%{HTTP:Authorization}]\n"
        "RewriteBase /\n"
        "RewriteRule ^index\\.php$ - [L]\n"
        "RewriteCond %{REQUEST_FILENAME} !-f\n"
        "RewriteCond %{REQUEST_FILENAME} !-d\n"
        "RewriteRule . /index.php [L]\n"
        "</IfModule>\n"
        "# END WordPress\n"
    )
    try:
        existing = htaccess.read_text(encoding="utf-8", errors="ignore") if htaccess.exists() else ""
    except OSError:
        existing = ""
    if "# BEGIN WordPress" in existing and "RewriteRule . /index.php" in existing:
        # Remplace le bloc WordPress pour garantir des règles valides (LiteSpeed)
        import re as _re

        new_content = _re.sub(
            r"# BEGIN WordPress.*?# END WordPress\n?",
            wp_rules,
            existing,
            count=1,
            flags=_re.DOTALL,
        )
        if new_content == existing and "# BEGIN WordPress" in existing:
            pass
        else:
            if "# BEGIN WordPress" not in new_content:
                new_content = existing.rstrip() + "\n\n" + wp_rules
            htaccess.write_text(new_content, encoding="utf-8")
            steps.append("htaccess_updated")
    else:
        # Conserve d'éventuelles règles hors WordPress
        prefix = existing.strip()
        if prefix and "# BEGIN WordPress" not in prefix:
            htaccess.write_text(prefix + "\n\n" + wp_rules, encoding="utf-8")
        else:
            htaccess.write_text(wp_rules, encoding="utf-8")
        steps.append("htaccess_written")
    try:
        os.chmod(htaccess, 0o644)
    except OSError:
        pass
    try:
        username = (site.owner.username or site.owner.system_username or "").strip()
        if username:
            _fix_ownership(docroot, username)
    except Exception:  # noqa: BLE001
        logger.debug("chown after permalink flush skip", exc_info=True)

    # Double flush après écriture .htaccess
    try:
        _run_wp(["rewrite", "flush", "--hard"], path=docroot, php_version=php_ver)
        steps.append("rewrite_flush_final")
    except VZoneAPIException:
        pass

    return {
        "permalink_structure": "/%postname%/",
        "htaccess": str(htaccess),
        "htaccess_exists": htaccess.is_file(),
        "steps": steps,
    }


def fix_wordpress_permalinks(site: WordPressSite) -> dict[str, Any]:
    """Corrige les 404 des pages WP (permaliens + .htaccess LiteSpeed)."""
    docroot = Path(site.document_root or "")
    if not docroot.is_dir():
        raise VZoneAPIException(
            detail="Document root WordPress introuvable.",
            code="wp_missing",
            status_code=404,
        )
    result = _flush_wp_rewrites(site)
    return {
        "site_id": site.pk,
        "domain": site.domain.name if site.domain_id else "",
        "site_url": site.site_url or _site_url(site.domain),
        "message": (
            f"Permaliens régénérés pour {site.domain.name}. "
            "Les pages /a-propos/, /blog/, etc. doivent répondre à nouveau."
        ),
        **result,
    }


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
.vz-leaf {
  display: inline-block;
  width: 0.7rem; height: 1.1rem;
  background: var(--vz-leaf);
  border-radius: 0 100% 0 100%;
  transform: rotate(-25deg);
  margin-right: 0.45rem;
  vertical-align: -0.1rem;
  box-shadow: 0 0 0 3px rgba(76,175,112,0.15);
}
.vz-hero::after {
  content: "";
  position: absolute; inset: auto 0 0 0; height: 4px;
  background: linear-gradient(90deg, transparent, var(--vz-leaf), transparent);
}
.vz-section--alt {
  background: var(--vz-mist);
  border-radius: 1.5rem;
  padding: clamp(1.5rem, 4vw, 2.5rem) 1.25rem;
  margin-bottom: 2.5rem;
}
.vz-timeline { list-style: none; padding: 0; margin: 0; }
.vz-timeline li {
  position: relative;
  padding: 0 0 1.5rem 1.5rem;
  border-left: 2px solid rgba(47,107,69,0.25);
}
.vz-timeline li::before {
  content: "";
  position: absolute; left: -0.4rem; top: 0.35rem;
  width: 0.7rem; height: 0.7rem; border-radius: 50%;
  background: var(--vz-leaf);
  box-shadow: 0 0 0 4px rgba(76,175,112,0.2);
}
.vz-timeline strong { color: var(--vz-forest); display: block; margin-bottom: 0.25rem; }
.site-footer, footer, .ast-footer-overlay {
  background: var(--vz-forest) !important;
  color: rgba(255,255,255,0.85) !important;
}
.site-footer a, footer a { color: #b8e0c4 !important; }
.entry-content { font-size: 1.05rem; }
.wp-block-post-title a, .entry-title a { text-decoration: none; }
button, .wp-block-button__link, .ast-button {
  border-radius: 999px !important;
  transition: transform .2s ease, box-shadow .2s ease !important;
}
button:hover, .wp-block-button__link:hover, .ast-button:hover {
  transform: translateY(-1px);
}
.vz-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  max-width: 1100px;
  margin: -1.5rem auto 2.5rem;
  padding: 0 1.25rem;
  position: relative;
  z-index: 2;
}
.vz-stat {
  background: #fff;
  border-radius: 1rem;
  padding: 1.25rem;
  text-align: center;
  border: 1px solid rgba(31,77,46,0.08);
  box-shadow: 0 8px 24px rgba(26,46,34,0.05);
}
.vz-stat strong { display: block; font-size: 1.75rem; color: var(--vz-moss); }
.vz-stat span { font-size: 0.85rem; color: #4a5d52; }
.vz-blog-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1.25rem; }
.vz-blog-card {
  background: #fff;
  border-radius: 1.25rem;
  overflow: hidden;
  border: 1px solid rgba(31,77,46,0.08);
  box-shadow: 0 10px 32px rgba(26,46,34,0.06);
  transition: transform .2s ease;
}
.vz-blog-card:hover { transform: translateY(-3px); }
.vz-blog-card img { width: 100%; height: 160px; object-fit: cover; display: block; }
.vz-blog-card div { padding: 1.15rem; }
.vz-blog-card h3 { margin: 0 0 0.35rem; font-size: 1.05rem; }
.vz-blog-card p { margin: 0; font-size: 0.9rem; color: #4a5d52; }
.vz-hero {
  position: relative;
  min-height: clamp(520px, 88vh, 820px);
  display: flex;
  align-items: flex-end;
  padding: clamp(2.5rem, 7vw, 5.5rem);
  border-radius: 0;
  overflow: hidden;
  background:
    linear-gradient(105deg, rgba(12,32,20,0.82) 0%, rgba(12,32,20,0.35) 55%, rgba(12,32,20,0.55) 100%),
    url("https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=2000&q=80")
    center/cover no-repeat;
  color: #fff;
  margin: 0 0 0;
}
.vz-hero__inner { max-width: 680px; animation: vzFadeUp .9s ease both; }
@keyframes vzFadeUp {
  from { opacity: 0; transform: translateY(18px); }
  to { opacity: 1; transform: translateY(0); }
}
.vz-hero__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.22em;
  opacity: 0.92;
  margin-bottom: 1rem;
  padding: 0.35rem 0.85rem;
  border: 1px solid rgba(255,255,255,0.35);
  border-radius: 999px;
  backdrop-filter: blur(6px);
  background: rgba(255,255,255,0.08);
}
.vz-hero h1 {
  color: #fff !important;
  font-size: clamp(2.6rem, 6.5vw, 4.2rem);
  line-height: 1.05;
  margin: 0 0 1.1rem;
  text-shadow: 0 4px 32px rgba(0,0,0,0.35);
}
.vz-hero p {
  font-size: clamp(1.08rem, 2.1vw, 1.3rem);
  opacity: 0.95;
  max-width: 34em;
  margin: 0 0 1.75rem;
  line-height: 1.55;
}
.vz-hero__actions { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; }
.vz-hero__scroll {
  position: absolute;
  left: 50%;
  bottom: 1.25rem;
  transform: translateX(-50%);
  font-size: 0.7rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  opacity: 0.75;
  animation: vzBounce 2s ease infinite;
}
@keyframes vzBounce {
  0%, 100% { transform: translateX(-50%) translateY(0); }
  50% { transform: translateX(-50%) translateY(6px); }
}
.vz-path {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  counter-reset: vzstep;
}
.vz-path article {
  position: relative;
  background: #fff;
  border-radius: 1.15rem;
  padding: 1.35rem 1.25rem 1.25rem;
  border: 1px solid rgba(31,77,46,0.08);
  box-shadow: 0 8px 28px rgba(26,46,34,0.05);
}
.vz-path article::before {
  counter-increment: vzstep;
  content: counter(vzstep);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem; height: 1.75rem;
  border-radius: 999px;
  background: var(--vz-mist);
  color: var(--vz-forest);
  font-weight: 700;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}
.vz-quote {
  max-width: 1100px;
  margin: 0 auto 3rem;
  padding: clamp(2rem, 5vw, 3rem);
  border-radius: 1.5rem;
  background:
    linear-gradient(135deg, rgba(31,77,46,0.92), rgba(47,107,69,0.88)),
    url("https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?auto=format&fit=crop&w=1600&q=70")
    center/cover;
  color: #fff;
  text-align: center;
}
.vz-quote p {
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(1.25rem, 3vw, 1.75rem);
  line-height: 1.45;
  margin: 0 0 0.75rem;
  max-width: 22em;
  margin-left: auto;
  margin-right: auto;
}
.vz-quote cite { opacity: 0.8; font-style: normal; font-size: 0.9rem; }
.vz-nav-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.75rem;
  max-width: 1100px;
  margin: 0 auto 2.5rem;
  padding: 0 1.25rem;
}
.vz-nav-strip a {
  display: block;
  text-align: center;
  text-decoration: none !important;
  color: var(--vz-forest) !important;
  background: #fff;
  border: 1px solid rgba(31,77,46,0.1);
  border-radius: 999px;
  padding: 0.7rem 1rem;
  font-weight: 600;
  font-size: 0.9rem;
  transition: background .2s ease, transform .2s ease;
}
.vz-nav-strip a:hover {
  background: var(--vz-mist);
  transform: translateY(-2px);
}
@media (max-width: 640px) {
  .vz-btn--ghost { display: inline-block; margin: 0; text-align: center; }
  .vz-hero { min-height: 78vh; align-items: center; }
}
"""


_HOME_HTML = """
<!-- wp:html -->
<div class="vz-hero">
  <div class="vz-hero__inner">
    <span class="vz-hero__eyebrow"><span class="vz-leaf"></span> Nature &amp; biodiversite</span>
    <h1>Echappee Verte</h1>
    <p>Un refuge immersif pour explorer forets, faune et paysages — ressentir, comprendre et proteger le vivant, pas a pas.</p>
    <div class="vz-hero__actions">
      <a class="vz-btn" href="#decouvrir">Commencer l'exploration</a>
      <a class="vz-btn vz-btn--ghost" href="/blog/">Lire le blog</a>
      <a class="vz-btn vz-btn--ghost" href="/randonnees/">Randonnees</a>
    </div>
  </div>
  <span class="vz-hero__scroll">Defiler</span>
</div>
<div class="vz-stats">
  <div class="vz-stat"><strong>120+</strong><span>Especes observees</span></div>
  <div class="vz-stat"><strong>48</strong><span>Sentiers recenses</span></div>
  <div class="vz-stat"><strong>12</strong><span>Actions locales</span></div>
  <div class="vz-stat"><strong>4</strong><span>Saisons a suivre</span></div>
</div>
<nav class="vz-nav-strip" aria-label="Sections">
  <a href="/biodiversite/">Biodiversite</a>
  <a href="/randonnees/">Randonnees</a>
  <a href="/galerie/">Galerie</a>
  <a href="/agenda/">Agenda</a>
  <a href="/ressources/">Ressources</a>
  <a href="/a-propos/">A propos</a>
</nav>
<div class="vz-section" id="decouvrir">
  <h2><span class="vz-leaf"></span>Notre mission</h2>
  <p class="vz-lead">Sensibiliser a la beaute du monde naturel et transmettre des gestes concrets pour la biodiversite — pres de chez vous comme au bout du monde.</p>
  <div class="vz-grid">
    <article class="vz-card">
      <div class="vz-card__icon">F</div>
      <h3>Forets &amp; paysages</h3>
      <p>Reportages immersifs sur les grands espaces, sentiers et canopees qui respirent encore.</p>
      <p><a href="/randonnees/">Explorer les sentiers →</a></p>
    </article>
    <article class="vz-card">
      <div class="vz-card__icon">B</div>
      <h3>Faune &amp; flore</h3>
      <p>Portraits d'especes, cycles des saisons et interactions invisibles du vivant.</p>
      <p><a href="/biodiversite/">Decouvrir la biodiversite →</a></p>
    </article>
    <article class="vz-card">
      <div class="vz-card__icon">A</div>
      <h3>Agir localement</h3>
      <p>Idees simples pour jardins, balcons et collectivites — chaque geste compte.</p>
      <p><a href="/agenda/">Voir l'agenda →</a></p>
    </article>
  </div>
</div>
<div class="vz-section vz-section--alt">
  <h2><span class="vz-leaf"></span>Par ou commencer ?</h2>
  <p class="vz-lead">Trois portes d'entree selon votre envie du moment — lecture, marche ou action.</p>
  <div class="vz-path">
    <article>
      <h3>Lire</h3>
      <p>Articles courts pour comprendre un ecosysteme en quelques minutes.</p>
      <p><a href="/blog/">Ouvrir le blog</a></p>
    </article>
    <article>
      <h3>Marcher</h3>
      <p>Idees de balades respectueuses, avec repères leave-no-trace.</p>
      <p><a href="/randonnees/">Voir les randonnees</a></p>
    </article>
    <article>
      <h3>Agir</h3>
      <p>Ateliers, nettoyages et initiatives a rejoindre pres de chez vous.</p>
      <p><a href="/agenda/">Consulter l'agenda</a></p>
    </article>
  </div>
</div>
<div class="vz-quote">
  <p>« La nature ne se contemple pas en silence seulement — elle se protege aussi par des gestes simples. »</p>
  <cite>— Echappee Verte</cite>
</div>
<div class="vz-section">
  <h2><span class="vz-leaf"></span>Derniers articles</h2>
  <p class="vz-lead">Le blog nature : recits, conseils et inspirations pour explorer sans abimer.</p>
  <div class="vz-blog-grid">
    <a class="vz-blog-card" href="/forets-a-explorer/" style="text-decoration:none;color:inherit">
      <img src="https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&amp;fit=crop&amp;w=600&amp;q=80" alt="Foret" />
      <div><h3>Les plus belles forets</h3><p>Sentiers sous canopee et forets anciennes.</p></div>
    </a>
    <a class="vz-blog-card" href="/biodiversite-locale/" style="text-decoration:none;color:inherit">
      <img src="https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?auto=format&amp;fit=crop&amp;w=600&amp;q=80" alt="Vallee" />
      <div><h3>Proteger pres de chez soi</h3><p>Haies, mares et plantes locales.</p></div>
    </a>
    <a class="vz-blog-card" href="/observer-nature/" style="text-decoration:none;color:inherit">
      <img src="https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&amp;fit=crop&amp;w=600&amp;q=80" alt="Montagne" />
      <div><h3>Observer sans deranger</h3><p>Photographier la faune en douceur.</p></div>
    </a>
    <a class="vz-blog-card" href="/randonnee-leave-no-trace/" style="text-decoration:none;color:inherit">
      <img src="https://images.unsplash.com/photo-1551632811-561732d1e306?auto=format&amp;fit=crop&amp;w=600&amp;q=80" alt="Randonnee" />
      <div><h3>Randonner proprement</h3><p>Checklist leave-no-trace.</p></div>
    </a>
  </div>
  <p style="margin-top:1.5rem"><a class="vz-btn" href="/blog/">Voir tout le blog</a></p>
</div>
<div class="vz-cta">
  <h2>Rejoignez l'echappee</h2>
  <p>Des recits, des images et des pistes concretes pour reconnecter les regards a la nature.</p>
  <a class="vz-btn" href="/a-propos/">En savoir plus</a>
  <a class="vz-btn vz-btn--ghost" href="/contact/">Nous ecrire</a>
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
  <h2><span class="vz-leaf"></span>Contact</h2>
  <p class="vz-lead">Une idee d'article, un partenariat local ou simplement un message ?</p>
  <div class="vz-card" style="max-width:520px">
    <p><strong>Email</strong><br>contact@nature.local</p>
    <p style="margin:0;color:#4a5d52">Remplacez cette adresse dans l'admin WordPress (page Contact).</p>
  </div>
</div>
<!-- /wp:html -->
"""

_BIODIV_HTML = """
<!-- wp:html -->
<div class="vz-section" style="padding-top:2rem">
  <h2><span class="vz-leaf"></span>La Biodiversite</h2>
  <p class="vz-lead">Proteger la faune et la flore sauvage, c'est proteger les equilibres qui nous nourrissent et nous inspirent.</p>
  <div class="vz-section--alt">
    <div class="vz-grid">
      <article class="vz-card"><h3>Habitats</h3><p>Forets, zones humides, haies et prairies : chaque milieu abrite un reseau d'especes.</p></article>
      <article class="vz-card"><h3>Gestes utiles</h3><p>Laisser un coin sauvage, planter local, eviter les pesticides, accueillir les pollinisateurs.</p></article>
      <article class="vz-card"><h3>Observer</h3><p>Inventaires citoyens, photos respectueuses, transmission aux associations locales.</p></article>
    </div>
  </div>
  <p><a class="vz-btn" href="/randonnees/">Voir les echappees</a></p>
</div>
<!-- /wp:html -->
"""

_RANDONNEES_HTML = """
<!-- wp:html -->
<div class="vz-section" style="padding-top:2rem">
  <h2><span class="vz-leaf"></span>Randonnees &amp; Echappees Vertes</h2>
  <p class="vz-lead">Des idees de balades pour respirer, ralentir et decouvrir les grands espaces sans les abimer.</p>
  <div class="vz-grid">
    <article class="vz-card">
      <img src="https://images.unsplash.com/photo-1551632811-561732d1e306?auto=format&amp;fit=crop&amp;w=900&amp;q=80" alt="Sentier foret" style="width:100%;height:180px;object-fit:cover;border-radius:0.85rem;margin-bottom:1rem" />
      <h3>Sous la canopee</h3>
      <p>Boucles familiales en foret : sols mous, lumiere filtre, silence des oiseaux.</p>
    </article>
    <article class="vz-card">
      <img src="https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&amp;fit=crop&amp;w=900&amp;q=80" alt="Crete" style="width:100%;height:180px;object-fit:cover;border-radius:0.85rem;margin-bottom:1rem" />
      <h3>Cretes &amp; panoramas</h3>
      <p>Itineraires pour s'evader, avec conseils de securite et respect des sentiers.</p>
    </article>
    <article class="vz-card">
      <img src="https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&amp;fit=crop&amp;w=900&amp;q=80" alt="Lac" style="width:100%;height:180px;object-fit:cover;border-radius:0.85rem;margin-bottom:1rem" />
      <h3>Lacs &amp; rivieres</h3>
      <p>Balades au fil de l'eau : rester sur les chemins, ne rien laisser derriere soi.</p>
    </article>
  </div>
</div>
<!-- /wp:html -->
"""

_AGENDA_HTML = """
<!-- wp:html -->
<div class="vz-section" style="padding-top:2rem">
  <h2><span class="vz-leaf"></span>Agenda Ecolo</h2>
  <p class="vz-lead">Initiatives locales, ateliers nature et nettoyages de sentiers — a personnaliser avec vos vrais evenements.</p>
  <div class="vz-section--alt">
    <ul class="vz-timeline">
      <li><strong>Printemps — Atelier haies locales</strong>Apprenez a planter des especes favorables aux oiseaux et insectes.</li>
      <li><strong>Ete — Sortie observation</strong>Balade guidee a l'aube pour reconnaitre chants et traces.</li>
      <li><strong>Automne — Nettoyage de sentiers</strong>Chantier citoyen pour garder les chemins propres et praticables.</li>
      <li><strong>Hiver — Conference biodiversite</strong>Echanges avec des naturalistes et associations du territoire.</li>
    </ul>
  </div>
  <p><a class="vz-btn" href="/contact/">Proposer un evenement</a></p>
</div>
<!-- /wp:html -->
"""

_BLOG_HTML = """
<!-- wp:html -->
<div class="vz-section" style="padding-top:2rem">
  <h2><span class="vz-leaf"></span>Blog Nature</h2>
  <p class="vz-lead">Articles, guides et recits pour explorer le vivant avec curiosite et respect.</p>
  <div class="vz-blog-grid">
    <a class="vz-blog-card" href="/forets-a-explorer/" style="text-decoration:none;color:inherit">
      <img src="https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&amp;fit=crop&amp;w=600&amp;q=80" alt="" />
      <div><h3>Les plus belles forets a explorer</h3><p>Canopees, sentiers et silence.</p></div>
    </a>
    <a class="vz-blog-card" href="/biodiversite-locale/" style="text-decoration:none;color:inherit">
      <img src="https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?auto=format&amp;fit=crop&amp;w=600&amp;q=80" alt="" />
      <div><h3>Proteger la biodiversite locale</h3><p>Gestes concrets au quotidien.</p></div>
    </a>
    <a class="vz-blog-card" href="/observer-nature/" style="text-decoration:none;color:inherit">
      <img src="https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&amp;fit=crop&amp;w=600&amp;q=80" alt="" />
      <div><h3>Observer sans deranger</h3><p>Ethique et technique photo.</p></div>
    </a>
    <a class="vz-blog-card" href="/randonnee-leave-no-trace/" style="text-decoration:none;color:inherit">
      <img src="https://images.unsplash.com/photo-1551632811-561732d1e306?auto=format&amp;fit=crop&amp;w=600&amp;q=80" alt="" />
      <div><h3>Randonner leave-no-trace</h3><p>Preparer sa sortie nature.</p></div>
    </a>
  </div>
</div>
<!-- /wp:html -->
"""

_FAQ_HTML = """
<!-- wp:html -->
<div class="vz-section" style="padding-top:2rem">
  <h2><span class="vz-leaf"></span>FAQ</h2>
  <div class="vz-section--alt">
    <div class="vz-grid">
      <article class="vz-card"><h3>Comment participer ?</h3><p>Consultez l'agenda ecolo ou contactez-nous pour proposer une action locale.</p></article>
      <article class="vz-card"><h3>Puis-je reutiliser les photos ?</h3><p>Merci de citer la source et de ne pas modifier les credits.</p></article>
      <article class="vz-card"><h3>Comment agir chez moi ?</h3><p>Page Biodiversite et articles du blog — gestes simples, impact reel.</p></article>
    </div>
  </div>
</div>
<!-- /wp:html -->
"""

_RESSOURCES_HTML = """
<!-- wp:html -->
<div class="vz-section" style="padding-top:2rem">
  <h2><span class="vz-leaf"></span>Ressources</h2>
  <p class="vz-lead">Liens et pistes pour aller plus loin — associations, guides terrain, outils citoyens.</p>
  <div class="vz-grid">
    <article class="vz-card"><h3>Guides naturalistes</h3><p>Reconnaitre oiseaux, traces et plantes en balade.</p></article>
    <article class="vz-card"><h3>Associations</h3><p>Rejoindre des collectifs locaux de protection du vivant.</p></article>
    <article class="vz-card"><h3>Inventaires participatifs</h3><p>Contribuer a la science citoyenne depuis son jardin.</p></article>
  </div>
</div>
<!-- /wp:html -->
"""

_POSTS = (
    (
        "Les plus belles forets a explorer",
        "forets-a-explorer",
        "Des sentiers sous canopee aux forets anciennes : pistes pour une echappee respectueuse du vivant.",
    ),
    (
        "Proteger la biodiversite pres de chez soi",
        "biodiversite-locale",
        "Haies, mares, plantes locales : gestes simples qui font une vraie difference pour les especes.",
    ),
    (
        "Faune et flore : observer sans deranger",
        "observer-nature",
        "Conseils de terrain pour photographier et decouvrir la nature en douceur.",
    ),
    (
        "Preparer une randonnee sans laisser de trace",
        "randonnee-leave-no-trace",
        "Checklist legere : eau, carte, sacs pour les dechets, et respect des habitats fragiles.",
    ),
    (
        "Jardins favorables aux pollinisateurs",
        "jardins-pollinisateurs",
        "Fleurs locales, abris et eau : accueillir abeilles et papillons sur son balcon.",
    ),
    (
        "Comprendre les ecosystemes forestiers",
        "ecosystemes-forestiers",
        "Du sol a la canopee : un reseau fragile a proteger.",
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
    try:
        return _beautify_wordpress_site_inner(site, theme=theme)
    except VZoneAPIException:
        raise
    except IndexError as exc:
        logger.exception("beautify IndexError site=%s", getattr(site, "pk", None))
        raise VZoneAPIException(
            detail=f"Erreur interne WordPress (index): {exc}",
            code="wp_beautify_index",
            status_code=500,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("beautify failed site=%s", getattr(site, "pk", None))
        raise VZoneAPIException(
            detail=f"Amelioration WordPress echouee: {exc}",
            code="wp_beautify_failed",
            status_code=502,
        ) from exc


def _beautify_wordpress_site_inner(site: WordPressSite, *, theme: str = "astra") -> dict:
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
        try:
            _run_wp(
                ["theme", "activate", "twentytwentyfour"],
                path=docroot,
                php_version=php_ver,
            )
            theme_slug = "twentytwentyfour"
            steps.append("theme:twentytwentyfour")
        except VZoneAPIException as exc:
            steps.append(f"theme_skip:{exc}")

    title = (site.title or "Echappee Verte").strip() or "Echappee Verte"
    tagline = "Nature, biodiversite & paysages"
    for opt, val in (
        ("blogname", title),
        ("blogdescription", tagline),
        ("timezone_string", "Europe/Paris"),
    ):
        try:
            _run_wp(["option", "update", opt, val], path=docroot, php_version=php_ver)
        except VZoneAPIException as exc:
            steps.append(f"opt_{opt}:{exc}")
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
    try:
        steps.append("css:" + (_wp_eval(site, css_php) or "done")[:80])
    except VZoneAPIException as exc:
        steps.append(f"css_err:{exc}")

    page_specs = (
        ("accueil", "Accueil", _HOME_HTML),
        ("blog", "Blog", _BLOG_HTML),
        ("a-propos", "A propos", _ABOUT_HTML),
        ("biodiversite", "La Biodiversite", _BIODIV_HTML),
        ("randonnees", "Randonnees", _RANDONNEES_HTML),
        ("galerie", "Galerie", _GALLERY_HTML),
        ("agenda", "Agenda Ecolo", _AGENDA_HTML),
        ("ressources", "Ressources", _RESSOURCES_HTML),
        ("faq", "FAQ", _FAQ_HTML),
        ("contact", "Contact", _CONTACT_HTML),
    )
    page_ids: dict[str, int] = {}
    for slug, page_title, html in page_specs:
        try:
            page_ids[slug] = _upsert_page_from_file(site, slug, page_title, html)
        except VZoneAPIException as exc:
            page_ids[slug] = 0
            steps.append(f"page_err_{slug}:{exc}")
    steps.append("pages:" + ",".join(f"{k}={v}" for k, v in page_ids.items()))

    required_slugs = ("accueil", "a-propos", "blog", "contact")
    missing = [s for s in required_slugs if not page_ids.get(s)]
    if missing:
        raise VZoneAPIException(
            detail=f"Pages WordPress non creees : {', '.join(missing)}. Verifiez wp-cli et permissions.",
            code="wp_pages_failed",
            status_code=502,
        )

    home_id = page_ids.get("accueil") or 0
    blog_id = page_ids.get("blog") or 0
    if home_id:
        try:
            _run_wp(["option", "update", "show_on_front", "page"], path=docroot, php_version=php_ver)
            _run_wp(
                ["option", "update", "page_on_front", str(home_id)],
                path=docroot,
                php_version=php_ver,
            )
            if blog_id:
                _run_wp(
                    ["option", "update", "page_for_posts", str(blog_id)],
                    path=docroot,
                    php_version=php_ver,
                )
            steps.append("front_page")
        except VZoneAPIException as exc:
            steps.append(f"front_page_err:{exc}")

    try:
        _wp_eval(
            site,
            "$term = term_exists('nature', 'category');\n"
            "if (!$term) { wp_insert_term('Nature', 'category', array('slug'=>'nature')); }\n"
            "echo 'cat_ok';\n",
        )
    except VZoneAPIException:
        pass

    posts_created = 0
    for ptitle, pslug, excerpt in _POSTS:
        body = (
            f"<p>{excerpt}</p>"
            "<p>La nature nous rappelle que chaque detail participe a un equilibre fragile. "
            "Prenez le temps d observer et de transmettre.</p>"
        )
        pid = _upsert_post(site, pslug, ptitle, excerpt, body)
        if pid > 0:
            posts_created += 1
    steps.append(f"posts:{posts_created}")

    ordered = [
        page_ids.get("accueil") or 0,
        page_ids.get("blog") or 0,
        page_ids.get("biodiversite") or 0,
        page_ids.get("randonnees") or 0,
        page_ids.get("galerie") or 0,
        page_ids.get("agenda") or 0,
        page_ids.get("a-propos") or 0,
        page_ids.get("ressources") or 0,
        page_ids.get("faq") or 0,
        page_ids.get("contact") or 0,
    ]
    menu_php = (
        "$menu_name = 'Principal';\n"
        "$menu = wp_get_nav_menu_object($menu_name);\n"
        "if (!$menu) { $menu_id = wp_create_nav_menu($menu_name); }\n"
        "else {\n"
        "  $menu_id = (int)$menu->term_id;\n"
        "  $items = wp_get_nav_menu_items($menu_id);\n"
        "  if (is_array($items)) { foreach ($items as $item) { wp_delete_post($item->ID, true); } }\n"
        "}\n"
        f"$pages = array({', '.join(str(int(x)) for x in ordered)});\n"
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
    try:
        steps.append((_wp_eval(site, menu_php) or "menu")[:40])
    except VZoneAPIException as exc:
        steps.append(f"menu_err:{exc}")

    _flush_wp_rewrites(site)
    steps.append("rewrite_flush")

    try:
        username = (site.owner.username or site.owner.system_username or "").strip()
        if username:
            _fix_ownership(docroot, username)
            _fix_ownership(docroot / ".vz-pages", username)
    except Exception:  # noqa: BLE001
        logger.debug("chown after beautify skip", exc_info=True)

    site.title = title
    site.save(update_fields=["title", "updated_at"])

    page_urls = {
        slug: f"{site.site_url or _site_url(site.domain)}/{slug}/"
        for slug, pid in page_ids.items()
        if pid
    }

    return {
        "site_id": site.pk,
        "domain": site.domain.name,
        "site_url": site.site_url or _site_url(site.domain),
        "theme": theme_slug,
        "style": "nature",
        "pages": page_ids,
        "page_urls": page_urls,
        "posts_created": posts_created,
        "steps": steps,
        "message": (
            f"Design nature applique sur {site.domain.name} "
            f"({len(page_ids)} pages, blog, {posts_created} articles, permaliens regeneres)."
        ),
    }
