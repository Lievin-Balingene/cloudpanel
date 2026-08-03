"""Génération des vhosts Nginx par domaine (priorité app > static)."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from apps.domains.models import Domain

logger = logging.getLogger(__name__)

SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True)
class DomainBackend:
    mode: str  # proxy | php | static | suspended
    docroot: str
    port: int = 0
    php_socket: str = ""
    app_label: str = ""


def nginx_domains_dir() -> Path:
    path = Path(
        getattr(settings, "VZONE_NGINX_DOMAINS_DIR", None)
        or (Path(settings.VZONE_DATA_ROOT) / "nginx" / "domains")
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def _web_stack_live() -> bool:
    mode = (getattr(settings, "VZONE_WEB_STACK", "auto") or "auto").lower()
    if mode == "live":
        return True
    if mode == "mock":
        return False
    return Path("/etc/nginx").is_dir() and shutil.which("nginx") is not None


def resolve_domain_backend(domain: Domain) -> DomainBackend:
    """
    Priorité :
    1. Suspendu → page 503
    2. Hostname panel (VZONE_PANEL_HOSTNAMES) → SPA panel
    3. App Python running liée au domaine
    4. App Node running liée au domaine
    5. Sélecteur PHP lié au domaine
    6. Fichiers statiques (document_root)
    Alias/parked héritent du parent pour l'app et le docroot.
    """
    target = domain
    if domain.domain_type in {Domain.DomainType.ALIAS, Domain.DomainType.PARKED} and domain.parent_id:
        target = domain.parent

    if domain.is_suspended or not domain.is_active or target.is_suspended or not target.is_active:
        return DomainBackend(mode="suspended", docroot=target.document_root or "/var/empty")

    panel_hosts = {
        h.strip().lower()
        for h in str(getattr(settings, "VZONE_PANEL_HOSTNAMES", "") or "").split(",")
        if h.strip()
    }
    if domain.name.lower() in panel_hosts or target.name.lower() in panel_hosts:
        panel_root = Path(getattr(settings, "VZONE_ROOT", "/opt/vzone")) / "frontend" / "dist"
        return DomainBackend(
            mode="panel",
            docroot=str(panel_root),
            app_label="vzone-panel",
        )

    names = {domain.name.lower(), target.name.lower()}
    docroot = target.document_root or ""

    try:
        from apps.python_apps.models import PythonApp

        py = (
            PythonApp.objects.filter(
                domain_name__in=names,
                is_active=True,
                status=PythonApp.Status.RUNNING,
                port__gt=0,
            )
            .order_by("-updated_at")
            .first()
        )
        if py:
            return DomainBackend(
                mode="proxy",
                docroot=docroot,
                port=py.port,
                app_label=f"python:{py.name}",
            )
    except Exception:  # noqa: BLE001
        logger.debug("resolve python skip", exc_info=True)

    try:
        from apps.node_apps.models import NodeApp

        node = (
            NodeApp.objects.filter(
                domain_name__in=names,
                is_active=True,
                status=NodeApp.Status.RUNNING,
                port__gt=0,
            )
            .order_by("-updated_at")
            .first()
        )
        if node:
            return DomainBackend(
                mode="proxy",
                docroot=docroot,
                port=node.port,
                app_label=f"node:{node.name}",
            )
    except Exception:  # noqa: BLE001
        logger.debug("resolve node skip", exc_info=True)

    try:
        from apps.php.models import PhpSelector

        php = (
            PhpSelector.objects.filter(domain_name__in=names, is_active=True)
            .select_related("php_version")
            .order_by("-updated_at")
            .first()
        )
        if php:
            sock = (
                php.php_version.fpm_socket
                or f"/run/php/php{php.php_version.version}-fpm.sock"
            )
            # Docroot = chemin du sélecteur si relatif au home
            from apps.files.services import personal_home

            php_root = personal_home(php.owner) / (php.relative_path or "public_html")
            return DomainBackend(
                mode="php",
                docroot=str(php_root if php_root.exists() else docroot),
                php_socket=sock,
                app_label=f"php:{php.php_version.version}",
            )
    except Exception:  # noqa: BLE001
        logger.debug("resolve php skip", exc_info=True)

    return DomainBackend(mode="static", docroot=docroot, app_label="static")


def _server_names(domain: Domain) -> str:
    names = [domain.name]
    if domain.domain_type in {
        Domain.DomainType.PRIMARY,
        Domain.DomainType.ADDON,
    }:
        www = f"www.{domain.name}"
        if www not in names:
            names.append(www)
    return " ".join(names)


def _conf_filename(hostname: str) -> str:
    safe = SAFE_NAME_RE.sub("_", hostname.lower())
    return f"{safe}.conf"


def _ssl_cert_paths(domain: Domain) -> tuple[str, str] | None:
    try:
        from apps.domains.ssl_services import cert_paths_for, has_active_cert_files

        if not has_active_cert_files(domain.name):
            return None
        _, fullchain, privkey = cert_paths_for(domain.name)
        return str(fullchain), str(privkey)
    except Exception:  # noqa: BLE001
        return None


def _location_body(backend: DomainBackend) -> str:
    if backend.mode == "suspended":
        return """
    location / {
        default_type text/html;
        return 503 '<html><body><h1>Account suspended</h1></body></html>';
    }
"""

    if backend.mode == "panel":
        docroot = backend.docroot or "/opt/vzone/frontend/dist"
        return f"""
    root {docroot};
    index index.html;

    location /assets/ {{
        try_files $uri =404;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }}

    location /api/ {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
    }}

    location /ws/ {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }}

    location /admin/ {{
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location /static/ {{
        alias /opt/vzone/backend/staticfiles/;
        expires 7d;
        access_log off;
    }}

    include /etc/nginx/snippets/vzone-phpmyadmin.inc;
    include /etc/nginx/snippets/vzone-roundcube.inc;

    location / {{
        try_files $uri $uri/ /index.html;
    }}
"""

    if backend.mode == "proxy" and backend.port > 0:
        return f"""
    location / {{
        proxy_pass http://127.0.0.1:{backend.port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
    }}
"""

    docroot = backend.docroot or "/var/empty"
    if backend.mode == "php" and backend.php_socket:
        return f"""
    root {docroot};
    index index.php index.html index.htm;

    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

    location ~ \\.php$ {{
        try_files $uri =404;
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        fastcgi_pass unix:{backend.php_socket};
        fastcgi_read_timeout 300;
    }}

    location ~* \\.(?:css|js|jpg|jpeg|gif|png|ico|svg|woff2?)$ {{
        expires 7d;
        access_log off;
        try_files $uri =404;
    }}
"""

    default_sock = ""
    for candidate in (
        "/run/php/php8.3-fpm.sock",
        "/run/php/php8.2-fpm.sock",
        "/run/php/php8.1-fpm.sock",
        "/run/php/php-fpm.sock",
    ):
        if Path(candidate).exists():
            default_sock = candidate
            break

    php_block = ""
    if default_sock:
        php_block = f"""
    location ~ \\.php$ {{
        try_files $uri =404;
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        fastcgi_pass unix:{default_sock};
        fastcgi_read_timeout 300;
    }}
"""

    return f"""
    root {docroot};
    index index.html index.htm index.php;

    location / {{
        try_files $uri $uri/ =404;
    }}
{php_block}
    location ~* \\.(?:css|js|jpg|jpeg|gif|png|ico|svg|woff2?)$ {{
        expires 7d;
        access_log off;
        try_files $uri =404;
    }}
"""


def render_vhost(domain: Domain, backend: DomainBackend) -> str:
    server_names = _server_names(domain)
    logs_prefix = SAFE_NAME_RE.sub("_", domain.name.lower())
    acme_root = getattr(settings, "VZONE_ACME_WEBROOT", None) or "/var/lib/vzone/acme"
    body = _location_body(backend)
    ssl_paths = _ssl_cert_paths(domain)

    http = f"""# V-zone domain vhost — {domain.name}
# backend={backend.mode} app={backend.app_label or '-'}
server {{
    listen 80;
    listen [::]:80;
    server_name {server_names};
    client_max_body_size 128m;

    access_log /var/log/nginx/{logs_prefix}.access.log;
    error_log  /var/log/nginx/{logs_prefix}.error.log;

    location ^~ /.well-known/acme-challenge/ {{
        root {acme_root};
        default_type "text/plain";
        allow all;
    }}
"""
    if ssl_paths:
        http += """
    location / {
        return 301 https://$host$request_uri;
    }
}
"""
    else:
        http += body + "\n}\n"

    if not ssl_paths:
        return http

    fullchain, privkey = ssl_paths
    https = f"""
server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {server_names};
    client_max_body_size 128m;

    ssl_certificate     {fullchain};
    ssl_certificate_key {privkey};
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_protocols TLSv1.2 TLSv1.3;

    access_log /var/log/nginx/{logs_prefix}.ssl.access.log;
    error_log  /var/log/nginx/{logs_prefix}.ssl.error.log;
{body}
}}
"""
    return http + https


def write_domain_vhost(domain: Domain) -> Path:
    backend = resolve_domain_backend(domain)
    conf = render_vhost(domain, backend)
    path = nginx_domains_dir() / _conf_filename(domain.name)
    path.write_text(conf, encoding="utf-8")
    logger.info("Vhost écrit %s (%s)", path, backend.mode)
    return path


def remove_domain_vhost(hostname: str) -> None:
    path = nginx_domains_dir() / _conf_filename(hostname)
    if path.exists():
        path.unlink()
        logger.info("Vhost retiré %s", path)


def reload_nginx() -> bool:
    if not _web_stack_live():
        return False
    # L'API tourne avec NoNewPrivileges — déléguer le reload à un helper root
    helper = Path("/usr/local/sbin/vzone-nginx-reload")
    if helper.is_file():
        # File drop pour l'agent path, + tentative directe (si root / polkit)
        flag = Path(
            getattr(settings, "VZONE_DATA_ROOT", "/var/lib/vzone")
        ) / "nginx" / "reload.requested"
        try:
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text(str(int(time.time())), encoding="utf-8")
        except OSError:
            pass
        try:
            subprocess.run(
                ["systemctl", "start", "vzone-nginx-reload.service"],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        # Fallback : exécuter le helper si on est root
        if os.geteuid() == 0:
            result = subprocess.run([str(helper)], capture_output=True, text=True)
            return result.returncode == 0
        return True

    test = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
    if test.returncode != 0:
        logger.error("nginx -t failed: %s", test.stderr)
        return False
    subprocess.run(["systemctl", "reload", "nginx"], check=False, capture_output=True)
    return True


def sync_all_domain_vhosts() -> int:
    """Régénère tous les vhosts actifs + reload Nginx."""
    # Map connection_upgrade pour websocket proxy
    map_file = Path("/etc/nginx/conf.d/vzone-map-upgrade.conf")
    if _web_stack_live() and not map_file.exists():
        try:
            map_file.write_text(
                "map $http_upgrade $connection_upgrade {\n"
                '    default upgrade;\n'
                '    \'\'      close;\n'
                "}\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    count = 0
    wanted = set()
    for domain in Domain.objects.select_related("parent", "owner").all():
        write_domain_vhost(domain)
        wanted.add(_conf_filename(domain.name))
        count += 1

    # Nettoyer les confs orphelines
    for path in nginx_domains_dir().glob("*.conf"):
        if path.name not in wanted:
            path.unlink(missing_ok=True)

    reload_nginx()
    return count


def sync_domain_vhost(domain: Domain) -> Path:
    path = write_domain_vhost(domain)
    # Alias/parked pointant ici : régénérer aussi les enfants qui partagent le backend
    for child in Domain.objects.filter(
        parent=domain,
        domain_type__in={Domain.DomainType.ALIAS, Domain.DomainType.PARKED},
    ):
        write_domain_vhost(child)
    reload_nginx()
    return path
