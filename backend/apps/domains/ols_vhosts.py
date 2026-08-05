"""Génération des vhosts OpenLiteSpeed (backend derrière Nginx)."""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from pathlib import Path

from django.conf import settings

from apps.domains.models import Domain

logger = logging.getLogger(__name__)

SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def ols_enabled() -> bool:
    """
    auto (défaut) → True si OLS est installé
    1/true → forcé on
    0/false → forcé off
    """
    raw = str(getattr(settings, "VZONE_OLS_ENABLED", "auto") or "auto").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return ols_installed()


def ols_ready() -> bool:
    return ols_enabled() and ols_installed()


def default_web_engine() -> str:
    """Moteur par défaut pour les nouveaux domaines (style cPanel = OLS si prêt)."""
    if getattr(settings, "VZONE_OLS_DEFAULT_ENGINE", True) and ols_ready():
        return Domain.WebEngine.OLS
    return Domain.WebEngine.NGINX


def ols_installed() -> bool:
    marker = Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "ols" / ".installed"
    root = Path(getattr(settings, "VZONE_OLS_ROOT", "/usr/local/lsws"))
    binary = root / "bin" / "lswsctrl"
    return marker.is_file() or binary.is_file()


def ols_listen() -> str:
    return str(getattr(settings, "VZONE_OLS_LISTEN", "127.0.0.1:8088") or "127.0.0.1:8088")


def ols_vhconf_dir() -> Path:
    path = Path(
        getattr(settings, "VZONE_OLS_VHCONF_DIR", None)
        or (Path(settings.VZONE_DATA_ROOT) / "ols" / "vhconf")
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def ols_maps_file() -> Path:
    path = Path(
        getattr(settings, "VZONE_OLS_MAPS_FILE", None)
        or (Path(settings.VZONE_DATA_ROOT) / "ols" / "vzone-vhosts.conf")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _safe_vh_name(hostname: str) -> str:
    return SAFE_NAME_RE.sub("_", hostname.lower())


def _lsphp_path(php_version: str) -> tuple[str, str]:
    """Retourne (ext_name, binary_path) pour lsphp."""
    ver = (php_version or "8.2").strip()
    parts = ver.split(".")
    if len(parts) >= 2:
        short = f"{parts[0]}{parts[1]}"
    else:
        short = ver.replace(".", "")[:2] or "82"
    name = f"lsphp{short}"
    root = Path(getattr(settings, "VZONE_OLS_ROOT", "/usr/local/lsws"))
    candidates = [
        root / name / "bin" / "lsphp",
        Path(f"/usr/local/lsws/{name}/bin/lsphp"),
    ]
    for c in candidates:
        if c.is_file():
            return name, str(c)
    fallback = root / "lsphp82" / "bin" / "lsphp"
    return "lsphp82", str(fallback)


def _php_version_for_domain(domain: Domain) -> str:
    try:
        from apps.php.models import PhpSelector

        names = {domain.name.lower()}
        if domain.parent_id and domain.parent:
            names.add(domain.parent.name.lower())
        php = (
            PhpSelector.objects.filter(domain_name__in=names, is_active=True)
            .select_related("php_version")
            .order_by("-updated_at")
            .first()
        )
        if php and php.php_version_id:
            return php.php_version.version
    except Exception:  # noqa: BLE001
        logger.debug("ols php version skip", exc_info=True)
    return "8.2"


def render_vhconf(*, domain: Domain, docroot: str, php_version: str) -> str:
    ext_name, lsphp_bin = _lsphp_path(php_version)
    sock = f"/tmp/lshttpd/{ext_name}-{_safe_vh_name(domain.name)}.sock"
    aliases = ""
    if domain.domain_type in {Domain.DomainType.PRIMARY, Domain.DomainType.ADDON}:
        aliases = f"www.{domain.name}"
    # docRoot absolu (sous vhRoot = home) — index.html en premier = page « Site prêt »
    return f"""# V-zone OLS vhconf — {domain.name}
docRoot                   {docroot.rstrip('/')}/
vhDomain                  {domain.name}
vhAliases                 {aliases}
enableGzip                1

errorlog /var/lib/vzone/ols/logs/{_safe_vh_name(domain.name)}.error.log {{
  useServer               0
  logLevel                ERROR
  rollingSize             10M
}}

accesslog /var/lib/vzone/ols/logs/{_safe_vh_name(domain.name)}.access.log {{
  useServer               0
  rollingSize             10M
}}

index  {{
  useServer               0
  indexFiles              index.html, index.htm, index.php
}}

scripthandler  {{
  add                     lsapi:{ext_name} php
}}

extprocessor {ext_name} {{
  type                    lsapi
  address                 uds://{sock}
  maxConns                35
  env                     PHP_LSAPI_CHILDREN=35
  initTimeout             60
  retryTimeout            0
  persistentConn          1
  respBuffer              0
  autoStart               1
  path                    {lsphp_bin}
  backlog                 100
  instances               1
  priority                0
  memSoftLimit            2047M
  memHardLimit            2047M
  procSoftLimit           400
  procHardLimit           500
}}

rewrite  {{
  enable                  1
  autoLoadHtaccess        1
}}

accessControl  {{
  allow                   *
}}
"""


def _vh_root_for_domain(domain: Domain, docroot: str) -> str:
    """vhRoot = home du compte (comme cPanel) ; docRoot reste le dossier du site."""
    try:
        from apps.files.services import personal_home

        if domain.owner_id:
            home = str(personal_home(domain.owner))
            root = Path(docroot).resolve()
            home_path = Path(home).resolve()
            if root == home_path or home_path in root.parents:
                return home
    except Exception:  # noqa: BLE001
        logger.debug("ols vhRoot fallback", exc_info=True)
    parent = Path(docroot).parent
    return str(parent) if str(parent) not in {".", ""} else docroot.rstrip("/")


def render_virtualhost_block(*, domain: Domain, docroot: str) -> str:
    vh = _safe_vh_name(domain.name)
    conf_path = ols_vhconf_dir() / f"{vh}.conf"
    vh_root = _vh_root_for_domain(domain, docroot)
    lines = [
        f"virtualhost {vh} {{",
        f"  vhRoot                  {vh_root}",
        f"  configFile              {conf_path}",
        "  allowSymbolLink         1",
        "  enableScript            1",
        "  restrained              1",
        # 2 = UID du fichier (comme cPanel) — sinon nobody → 404 sur /home/...
        "  setUIDMode              2",
        "}",
        "",
    ]
    return "\n".join(lines)


def render_listener_maps(domains: list[Domain]) -> str:
    """Listener local + maps Host → virtualhost."""
    lines = [
        "# Generated by V-zone — OpenLiteSpeed backend (do not edit)",
        "",
        "listener vzoneHttp {",
        f"  address                 {ols_listen()}",
        "  secure                  0",
        "  map                     DEFAULT vzoneDefault",
    ]
    for domain in domains:
        vh = _safe_vh_name(domain.name)
        lines.append(f"  map                     {domain.name} {vh}")
        if domain.domain_type in {Domain.DomainType.PRIMARY, Domain.DomainType.ADDON}:
            lines.append(f"  map                     www.{domain.name} {vh}")
    lines.append("}")
    lines.append("")
    lines.append("virtualhost vzoneDefault {")
    lines.append("  vhRoot                  /var/lib/vzone/ols/default")
    lines.append("  configFile              /var/lib/vzone/ols/vhconf/vzoneDefault.conf")
    lines.append("  allowSymbolLink         1")
    lines.append("  enableScript            1")
    lines.append("  restrained              1")
    lines.append("  setUIDMode              0")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def uses_ols_engine(domain: Domain) -> bool:
    """True si le domaine doit être servi par OLS (PHP/static seulement)."""
    if not ols_enabled():
        return False
    engine = getattr(domain, "web_engine", Domain.WebEngine.NGINX) or Domain.WebEngine.NGINX
    return engine == Domain.WebEngine.OLS


def write_ols_vhost(domain: Domain, *, docroot: str) -> Path | None:
    if not uses_ols_engine(domain):
        remove_ols_vhost(domain.name)
        return None
    if not ols_installed():
        logger.warning("OLS demandé pour %s mais non installé", domain.name)
        return None

    php_ver = _php_version_for_domain(domain)
    vh = _safe_vh_name(domain.name)
    vhconf = ols_vhconf_dir() / f"{vh}.conf"
    vhconf.write_text(
        render_vhconf(domain=domain, docroot=docroot or "/var/empty", php_version=php_ver),
        encoding="utf-8",
    )
    # Keep individual vh block file for debugging / partial includes
    block_path = Path(
        getattr(settings, "VZONE_OLS_VHOSTS_DIR", None)
        or (Path(settings.VZONE_DATA_ROOT) / "ols" / "vhosts")
    )
    block_path.mkdir(parents=True, exist_ok=True)
    (block_path / f"{vh}.conf").write_text(
        render_virtualhost_block(domain=domain, docroot=docroot or "/var/empty"),
        encoding="utf-8",
    )
    return vhconf


def remove_ols_vhost(hostname: str) -> None:
    vh = _safe_vh_name(hostname)
    for base in (ols_vhconf_dir(), Path(getattr(settings, "VZONE_OLS_VHOSTS_DIR", None) or Path(settings.VZONE_DATA_ROOT) / "ols" / "vhosts")):
        path = Path(base) / f"{vh}.conf"
        if path.exists():
            path.unlink(missing_ok=True)


def rebuild_ols_maps() -> int:
    """Régénère vzone-vhosts.conf (listener maps + virtualhost blocks) pour tous les domaines OLS."""
    if not ols_enabled():
        return 0

    qs = (
        Domain.objects.filter(web_engine=Domain.WebEngine.OLS)
        .exclude(is_active=False)
        .select_related("parent", "owner")
        .order_by("name")
    )
    domains: list[Domain] = []
    blocks: list[str] = []
    for domain in qs:
        # Skip panel hostnames
        try:
            from apps.domains.vhosts import is_panel_hostname, resolve_domain_backend

            if is_panel_hostname(domain.name):
                remove_ols_vhost(domain.name)
                continue
            backend = resolve_domain_backend(domain)
            # Python/Node/suspended/panel → pas d'OLS
            if backend.mode in {"proxy", "suspended", "panel"}:
                remove_ols_vhost(domain.name)
                continue
            docroot = backend.docroot or domain.document_root or "/var/empty"
            write_ols_vhost(domain, docroot=docroot)
            domains.append(domain)
            blocks.append(render_virtualhost_block(domain=domain, docroot=docroot))
        except Exception:  # noqa: BLE001
            logger.exception("rebuild OLS skip %s", domain.name)

    content = render_listener_maps(domains) + "\n" + "\n".join(blocks) + "\n"
    maps = ols_maps_file()
    maps.write_text(content, encoding="utf-8")
    logger.info("OLS maps rebuilt (%s domains) → %s", len(domains), maps)
    return len(domains)


def reload_ols() -> bool:
    if not ols_installed():
        return False
    helper = Path("/usr/local/sbin/vzone-ols-reload")
    flag = Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")) / "ols" / "reload.requested"
    try:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(str(int(time.time())), encoding="utf-8")
    except OSError:
        pass
    try:
        subprocess.run(
            ["systemctl", "start", "vzone-ols-reload.service"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    if helper.is_file() and os.geteuid() == 0:
        result = subprocess.run([str(helper)], capture_output=True, text=True)
        return result.returncode == 0
    return True


def adopt_php_domains_to_ols() -> dict:
    """Passe tous les domaines PHP/static éligibles en web_engine=ols + resync."""
    if not ols_ready():
        return {"ok": False, "error": "OLS non prêt", "updated": 0}

    from apps.domains.vhosts import is_panel_hostname, resolve_domain_backend, sync_all_domain_vhosts

    updated = 0
    skipped = 0
    for domain in Domain.objects.select_related("parent", "owner").all():
        if is_panel_hostname(domain.name):
            skipped += 1
            continue
        if domain.web_engine == Domain.WebEngine.OLS:
            skipped += 1
            continue
        backend = resolve_domain_backend(domain)
        if backend.mode in {"proxy", "suspended", "panel"}:
            skipped += 1
            continue
        domain.web_engine = Domain.WebEngine.OLS
        domain.save(update_fields=["web_engine", "updated_at"])
        updated += 1

    sync_all_domain_vhosts()
    return {"ok": True, "updated": updated, "skipped": skipped}


def ols_overview() -> dict:
    data_root = Path(getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone"))
    ols_dir = data_root / "ols"
    vhconf = ols_vhconf_dir()
    count = len(list(vhconf.glob("*.conf"))) if vhconf.is_dir() else 0
    count = max(0, count - (1 if (vhconf / "vzoneDefault.conf").is_file() else 0))

    version = ""
    root = Path(getattr(settings, "VZONE_OLS_ROOT", "/usr/local/lsws"))
    for candidate in (root / "VERSION", root / "VERSION.txt"):
        if candidate.is_file():
            try:
                version = candidate.read_text(encoding="utf-8", errors="replace").strip()[:80]
                break
            except OSError:
                pass
    if not version:
        lshttpd = root / "bin" / "lshttpd"
        if lshttpd.is_file():
            try:
                proc = subprocess.run(
                    [str(lshttpd), "-v"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                version = (proc.stdout or proc.stderr or "").strip().splitlines()[0][:120]
            except (OSError, subprocess.TimeoutExpired, IndexError):
                version = ""

    active = False
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "lshttpd"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        active = (proc.stdout or "").strip() == "active"
        if not active:
            proc = subprocess.run(
                ["systemctl", "is-active", "lsws"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            active = (proc.stdout or "").strip() == "active"
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        active = False

    ready = ols_ready()
    mode = str(getattr(settings, "VZONE_OLS_ENABLED", "auto") or "auto")
    return {
        "enabled": ols_enabled(),
        "enabled_mode": mode,
        "installed": ols_installed(),
        "ready": ready,
        "active": active,
        "listen": ols_listen(),
        "version": version or ("OpenLiteSpeed" if ols_installed() else ""),
        "vhosts": count,
        "domains_ols": Domain.objects.filter(web_engine=Domain.WebEngine.OLS).count(),
        "domains_nginx": Domain.objects.filter(web_engine=Domain.WebEngine.NGINX).count(),
        "default_engine": default_web_engine(),
        "data_dir": str(ols_dir),
        "maps_file": str(ols_maps_file()),
        "hint": (
            None
            if ready
            else (
                "OpenLiteSpeed n'est pas prêt. "
                "Installez: sudo bash /opt/vzone-src/scripts/install-openlitespeed.sh"
            )
        ),
        "status_message": (
            "Prêt — les nouveaux domaines utilisent OpenLiteSpeed par défaut (comme cPanel)."
            if ready
            else "En attente d'installation ou désactivé."
        ),
    }
