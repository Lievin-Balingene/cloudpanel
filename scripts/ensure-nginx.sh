#!/usr/bin/env bash
# Installe Nginx V-zone : parking (default) + panel (hostnames) + domaines clients.
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
SRC="${1:-${VZONE_ROOT}/deploy/nginx/vzone.conf}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_PARKING="${VZONE_ROOT}/deploy/nginx/parking.html"

[[ -f "$SRC" ]] || { echo "Config introuvable: $SRC"; exit 1; }

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

PANEL_HOSTS="${VZONE_PANEL_HOSTNAMES:-vpanel.vzonecloud.co.uk}"
PANEL_HOSTS="${PANEL_HOSTS//,/ }"
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
PANEL_NAMES="$PANEL_HOSTS"
for extra in localhost 127.0.0.1 ${HOST_IP}; do
  [[ -n "$extra" ]] || continue
  case " ${PANEL_NAMES} " in
    *" ${extra} "*) ;;
    *) PANEL_NAMES="${PANEL_NAMES} ${extra}" ;;
  esac
done
PANEL_NAMES="$(echo "$PANEL_NAMES" | xargs)"
PANEL_PRIMARY="$(echo "$PANEL_HOSTS" | awk '{print $1}')"

echo "[vzone] Panel server_name: ${PANEL_NAMES}"

mkdir -p /etc/nginx/snippets /var/lib/vzone/parking /var/lib/vzone/acme

if [[ ! -f /etc/nginx/snippets/vzone-phpmyadmin.inc ]]; then
  cat > /etc/nginx/snippets/vzone-phpmyadmin.inc <<'EOF'
location = /phpmyadmin { return 302 /phpmyadmin/; }
location /phpmyadmin/ {
    default_type text/plain;
    return 503 "phpMyAdmin n'est pas encore installé.\n";
}
EOF
fi

if [[ ! -f /etc/nginx/snippets/vzone-roundcube.inc ]]; then
  cat > /etc/nginx/snippets/vzone-roundcube.inc <<'EOF'
location = /webmail { return 302 /webmail/; }
location /webmail/ {
    default_type text/plain;
    return 503 "Roundcube n'est pas encore installé.\n";
}
EOF
fi

if [[ -f "$REPO_PARKING" ]]; then
  install -m 644 "$REPO_PARKING" /var/lib/vzone/parking/index.html
else
  printf '%s\n' '<h1>Site not configured</h1>' > /var/lib/vzone/parking/index.html
fi
chmod -R a+rX /var/lib/vzone/parking /var/lib/vzone/acme

DOMAINS_DIR="${VZONE_NGINX_DOMAINS_DIR:-/var/lib/vzone/nginx/domains}"
mkdir -p "$DOMAINS_DIR"
chown -R vzone:vzone /var/lib/vzone/nginx /var/lib/vzone/acme 2>/dev/null || true
chmod 755 "$DOMAINS_DIR"

cat > /etc/nginx/conf.d/vzone-map-upgrade.conf <<'EOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
EOF
cat > /etc/nginx/conf.d/vzone-domains-include.conf <<EOF
include ${DOMAINS_DIR}/*.conf;
EOF
if [[ ! -f "${DOMAINS_DIR}/.keep.conf" ]]; then
  echo "# vzone domains placeholder" > "${DOMAINS_DIR}/.keep.conf"
fi

TMP="$(mktemp)"
export TMP PANEL_NAMES PANEL_PRIMARY
export SSL_DIR="/var/lib/vzone/ssl/${PANEL_PRIMARY}"
cp "$SRC" "$TMP"

python3 - <<'PY'
import os
from pathlib import Path

tmp = Path(os.environ["TMP"])
text = tmp.read_text(encoding="utf-8")
panel_names = os.environ["PANEL_NAMES"]
primary = (os.environ.get("PANEL_PRIMARY") or "").strip()
ssl_dir = Path(os.environ.get("SSL_DIR") or "")

text = text.replace("__PANEL_SERVER_NAMES__", panel_names)

ssl_block = ""
fullchain = ssl_dir / "fullchain.pem"
privkey = ssl_dir / "privkey.pem"
if primary and fullchain.is_file() and privkey.is_file():
    ssl_block = f"""
server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {panel_names};

    client_max_body_size 128m;

    ssl_certificate     {fullchain};
    ssl_certificate_key {privkey};
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_protocols TLSv1.2 TLSv1.3;

    root /opt/vzone/frontend/dist;
    index index.html;

    location /assets/ {{
        try_files $uri =404;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }}

    location /api/ {{
        proxy_pass http://vzone_asgi;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
    }}

    location /ws/ {{
        proxy_pass http://vzone_asgi;
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
        proxy_pass http://vzone_asgi;
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
}}
"""

text = text.replace("# __PANEL_SSL_SERVER__", ssl_block)
tmp.write_text(text, encoding="utf-8")
print(f"[vzone] SSL panel: {'oui' if ssl_block else 'non'}")
PY

rm -f /etc/nginx/sites-enabled/default \
      /etc/nginx/sites-enabled/default.bak \
      /etc/nginx/sites-enabled/000-default \
      /etc/nginx/conf.d/default.conf 2>/dev/null || true

if [[ -d /etc/nginx/sites-available ]]; then
  install -m 644 "$TMP" /etc/nginx/sites-available/vzone
  ln -sfn /etc/nginx/sites-available/vzone /etc/nginx/sites-enabled/vzone
  for f in /etc/nginx/sites-enabled/*; do
    base="$(basename "$f")"
    [[ "$base" == "vzone" ]] && continue
    [[ -e "$f" ]] || continue
    if grep -q "default_server" "$f" 2>/dev/null; then
      echo "[vzone] Désactivation de $base (conflit default_server)"
      rm -f "$f"
    fi
  done
else
  install -m 644 "$TMP" /etc/nginx/conf.d/vzone.conf
fi
rm -f "$TMP"

if [[ ! -f "${VZONE_ROOT}/frontend/dist/index.html" ]]; then
  echo "[vzone] ERREUR: ${VZONE_ROOT}/frontend/dist/index.html manquant"
  exit 1
fi
chmod -R a+rX "${VZONE_ROOT}/frontend" || true
chmod a+x /opt /opt/vzone /opt/vzone/frontend 2>/dev/null || true

nginx -t
systemctl reload nginx || systemctl restart nginx
sleep 1

PANEL_TEST_HOST="$PANEL_PRIMARY"
echo "[vzone] Nginx OK — parking default + panel sur ${PANEL_TEST_HOST}"
code_park="$(curl -s -o /dev/null -w "%{http_code}" -H "Host: unknown.invalid" http://127.0.0.1/ || true)"
code_panel="$(curl -s -o /dev/null -w "%{http_code}" -H "Host: ${PANEL_TEST_HOST}" http://127.0.0.1/login || true)"
echo "[vzone] GET Host unknown → HTTP ${code_park} (parking attendu)"
echo "[vzone] GET Host ${PANEL_TEST_HOST}/login → HTTP ${code_panel} (panel)"
