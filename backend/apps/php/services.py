"""Services PHP multi-version : catalogue, sélecteurs, php.ini, pools FPM."""
from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException
from apps.files.services import user_home
from apps.php.models import PhpSelector, PhpVersion

logger = logging.getLogger(__name__)

PATH_RE = re.compile(r"^[a-zA-Z0-9._/-]+$")

DEFAULT_INI = {
    "memory_limit": "256M",
    "max_execution_time": "60",
    "upload_max_filesize": "64M",
    "post_max_size": "64M",
    "display_errors": "Off",
    "date.timezone": "UTC",
}

DEFAULT_EXTENSIONS = ["mysqli", "pdo_mysql", "gd", "mbstring", "xml", "curl", "zip", "opcache"]

DEFAULT_VERSIONS = (
    ("8.1", "/usr/bin/php8.1", "/run/php/php8.1-fpm.sock"),
    ("8.2", "/usr/bin/php8.2", "/run/php/php8.2-fpm.sock"),
    ("8.3", "/usr/bin/php8.3", "/run/php/php8.3-fpm.sock"),
    ("8.4", "/usr/bin/php8.4", "/run/php/php8.4-fpm.sock"),
)


def selectors_qs(user: User) -> QuerySet[PhpSelector]:
    qs = PhpSelector.objects.select_related("owner", "php_version")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def versions_qs() -> QuerySet[PhpVersion]:
    return PhpVersion.objects.filter(is_available=True)


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_PHP_PROVISION_MODE", "auto").lower()
    return mode if mode in {"auto", "live", "mock"} else "auto"


def config_root() -> Path:
    root = Path(getattr(settings, "VZONE_PHP_CONFIG_DIR", None) or (Path(settings.VZONE_DATA_ROOT) / "php"))
    root.mkdir(parents=True, exist_ok=True)
    (root / "pools").mkdir(exist_ok=True)
    (root / "ini").mkdir(exist_ok=True)
    return root


def ensure_default_versions() -> list[PhpVersion]:
    """Crée le catalogue de versions si vide."""
    if PhpVersion.objects.exists():
        return list(PhpVersion.objects.all())
    created: list[PhpVersion] = []
    for idx, (ver, binary, sock) in enumerate(DEFAULT_VERSIONS):
        exists = Path(binary).exists() if provision_mode() != "mock" else False
        obj = PhpVersion.objects.create(
            version=ver,
            binary_path=binary if exists else "",
            fpm_socket=sock if exists else "",
            is_available=True,
            is_default=(idx == 2),  # 8.3 par défaut
            notes="provisionné automatiquement" if not exists else "détecté",
        )
        created.append(obj)
    return created


def discover_system_versions() -> list[PhpVersion]:
    """Détecte les binaires phpX.Y sur le système (mode live/auto)."""
    ensure_default_versions()
    if provision_mode() == "mock":
        return list(PhpVersion.objects.all())
    updated = []
    for ver, binary, sock in DEFAULT_VERSIONS:
        found = shutil.which(f"php{ver}") or (binary if Path(binary).exists() else None)
        obj, _ = PhpVersion.objects.update_or_create(
            version=ver,
            defaults={
                "binary_path": found or "",
                "fpm_socket": sock if Path(sock).exists() else "",
                "is_available": bool(found),
            },
        )
        updated.append(obj)
    if not PhpVersion.objects.filter(is_default=True).exists():
        first = PhpVersion.objects.filter(is_available=True).order_by("-version").first()
        if first:
            first.is_default = True
            first.save()
    return updated


def resolve_selector_path(owner: User, relative_path: str) -> tuple[str, Path]:
    rel = (relative_path or "public_html").replace("\\", "/").strip("/")
    if not rel or ".." in Path(rel).parts or not PATH_RE.match(rel):
        raise VZoneAPIException(detail="Chemin PHP invalide.", code="invalid_path", status_code=400)
    home = user_home(owner)
    target = (home / rel).resolve()
    try:
        target.relative_to(home)
    except ValueError as exc:
        raise VZoneAPIException(
            detail="Chemin hors du home autorisé.",
            code="path_forbidden",
            status_code=403,
        ) from exc
    target.mkdir(parents=True, exist_ok=True)
    return rel, target


def write_user_ini(selector: PhpSelector, app_root: Path) -> Path:
    settings_map = {**DEFAULT_INI, **(selector.ini_settings or {})}
    lines = [f"{k} = {v}" for k, v in settings_map.items()]
    path = app_root / ".user.ini"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Copie centralisée
    central = config_root() / "ini" / f"{selector.owner_id}_{selector.pk or 'new'}.ini"
    central.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def write_fpm_pool(selector: PhpSelector) -> Path:
    pool_name = re.sub(
        r"[^a-zA-Z0-9_.-]",
        "_",
        f"{selector.owner.username}_{selector.relative_path.replace('/', '_')}",
    )
    sock = selector.php_version.fpm_socket or f"/run/php/php{selector.php_version.version}-fpm.sock"
    content = f"""; V-zone PHP-FPM pool — {selector.owner.username}
[{pool_name}]
user = nobody
group = nobody
listen = {sock}
pm = ondemand
pm.max_children = 10
pm.process_idle_timeout = 10s
chdir = {user_home(selector.owner) / selector.relative_path}
php_admin_value[open_basedir] = {user_home(selector.owner)}:/tmp
php_admin_value[disable_functions] = exec,passthru,shell_exec,system
"""
    path = config_root() / "pools" / f"{pool_name}.conf"
    path.write_text(content, encoding="utf-8")
    return path


def write_htaccess_handler(selector: PhpSelector, app_root: Path) -> Path:
    """Écrit un .htaccess hint pour MultiPHP (Apache)."""
    path = app_root / ".htaccess"
    marker_start = "# BEGIN Vzone PHP"
    marker_end = "# END Vzone PHP"
    block = (
        f"{marker_start}\n"
        f"# php_version {selector.php_version.version}\n"
        f"# handler {selector.handler}\n"
        f"AddHandler application/x-httpd-php{selector.php_version.version.replace('.', '')} .php\n"
        f"{marker_end}\n"
    )
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker_start in existing:
        before = existing.split(marker_start)[0]
        after = existing.split(marker_end)[-1] if marker_end in existing else ""
        existing = before + block + after.lstrip("\n")
    else:
        existing = existing.rstrip() + ("\n\n" if existing.strip() else "") + block
    path.write_text(existing, encoding="utf-8")
    return path


def write_selector_meta(selector: PhpSelector) -> Path:
    root = config_root() / "selectors"
    root.mkdir(exist_ok=True)
    path = root / f"{selector.owner_id}_{selector.pk}.json"
    path.write_text(
        json.dumps(
            {
                "id": selector.pk,
                "owner": selector.owner.username,
                "version": selector.php_version.version,
                "path": selector.relative_path,
                "domain": selector.domain_name,
                "handler": selector.handler,
                "ini": selector.ini_settings,
                "extensions": selector.extensions,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


@transaction.atomic
def create_selector(
    *,
    owner: User,
    php_version_id: int,
    relative_path: str = "public_html",
    domain_name: str = "",
    handler: str = PhpSelector.Handler.FPM,
    ini_settings: dict | None = None,
    extensions: list | None = None,
    notes: str = "",
) -> PhpSelector:
    ensure_default_versions()
    version = PhpVersion.objects.filter(pk=php_version_id, is_available=True).first()
    if version is None:
        raise VZoneAPIException(detail="Version PHP introuvable.", code="version_not_found", status_code=404)
    if handler not in PhpSelector.Handler.values:
        raise VZoneAPIException(detail="Handler invalide.", code="invalid_handler", status_code=400)

    rel, app_root = resolve_selector_path(owner, relative_path)
    if PhpSelector.objects.filter(owner=owner, relative_path=rel).exists():
        raise VZoneAPIException(
            detail="Un sélecteur existe déjà pour ce chemin.",
            code="exists",
            status_code=400,
        )

    selector = PhpSelector.objects.create(
        owner=owner,
        php_version=version,
        relative_path=rel,
        domain_name=domain_name.strip().lower(),
        handler=handler,
        ini_settings=ini_settings if ini_settings is not None else dict(DEFAULT_INI),
        extensions=extensions if extensions is not None else list(DEFAULT_EXTENSIONS),
        notes=notes,
    )
    write_user_ini(selector, app_root)
    write_htaccess_handler(selector, app_root)
    write_fpm_pool(selector)
    write_selector_meta(selector)
    return selector


@transaction.atomic
def update_selector(
    selector: PhpSelector,
    *,
    php_version_id: int | None = None,
    domain_name: str | None = None,
    handler: str | None = None,
    ini_settings: dict | None = None,
    extensions: list | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
) -> PhpSelector:
    if php_version_id is not None:
        version = PhpVersion.objects.filter(pk=php_version_id, is_available=True).first()
        if version is None:
            raise VZoneAPIException(detail="Version PHP introuvable.", code="version_not_found", status_code=404)
        selector.php_version = version
    if domain_name is not None:
        selector.domain_name = domain_name.strip().lower()
    if handler is not None:
        if handler not in PhpSelector.Handler.values:
            raise VZoneAPIException(detail="Handler invalide.", code="invalid_handler", status_code=400)
        selector.handler = handler
    if ini_settings is not None:
        selector.ini_settings = ini_settings
    if extensions is not None:
        selector.extensions = extensions
    if notes is not None:
        selector.notes = notes
    if is_active is not None:
        selector.is_active = is_active
    selector.save()

    _, app_root = resolve_selector_path(selector.owner, selector.relative_path)
    write_user_ini(selector, app_root)
    write_htaccess_handler(selector, app_root)
    write_fpm_pool(selector)
    write_selector_meta(selector)
    return selector


@transaction.atomic
def delete_selector(selector: PhpSelector) -> None:
    meta = config_root() / "selectors" / f"{selector.owner_id}_{selector.pk}.json"
    if meta.exists():
        meta.unlink(missing_ok=True)
    pool_name = re.sub(
        r"[^a-zA-Z0-9_.-]",
        "_",
        f"{selector.owner.username}_{selector.relative_path.replace('/', '_')}",
    )
    pool = config_root() / "pools" / f"{pool_name}.conf"
    if pool.exists():
        pool.unlink(missing_ok=True)
    selector.delete()


@transaction.atomic
def set_default_version(version_id: int) -> PhpVersion:
    version = PhpVersion.objects.filter(pk=version_id).first()
    if version is None:
        raise VZoneAPIException(detail="Version introuvable.", code="version_not_found", status_code=404)
    version.is_default = True
    version.is_available = True
    version.save()
    return version


def overview_for(user: User) -> dict:
    ensure_default_versions()
    selectors = selectors_qs(user)
    versions = versions_qs()
    return {
        "versions": versions.count(),
        "default_version": versions.filter(is_default=True).values_list("version", flat=True).first(),
        "selectors": selectors.count(),
        "active_selectors": selectors.filter(is_active=True).count(),
        "provision_mode": provision_mode(),
    }
