#!/usr/bin/env bash
# Installe Nginx V-zone : panel = default_server (IP OK) + vhosts domaines.
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
SRC="${1:-${VZONE_ROOT}/deploy/nginx/vzone.conf}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"

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
PANEL_NAMES="_ ${PANEL_HOSTS} localhost 127.0.0.1"
[[ -n "$HOST_IP" ]] && PANEL_NAMES="${PANEL_NAMES} ${HOST_IP}"
PANEL_NAMES="$(echo "$PANEL_NAMES" | xargs)"
PANEL_PRIMARY="$(echo "$PANEL_HOSTS" | awk '{print $1}')"

echo "[vzone] Panel server_name: ${PANEL_NAMES}"

export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq ssl-cert 2>/dev/null || true
if [[ ! -f /etc/ssl/certs/ssl-cert-snakeoil.pem || ! -f /etc/ssl/private/ssl-cert-snakeoil.key ]]; then
  make-ssl-cert generate-default-snakeoil --force-overwrite >/dev/null 2>&1 || \
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout /etc/ssl/private/ssl-cert-snakeoil.key \
    -out /etc/ssl/certs/ssl-cert-snakeoil.pem \
    -days 3650 -subj "/CN=vzone-panel" 2>/dev/null || true
fi

# www-data doit lire les clés SSL (sinon HTTPS → 500 nginx)
usermod -aG ssl-cert www-data 2>/dev/null || true
chmod 644 /etc/ssl/certs/ssl-cert-snakeoil.pem 2>/dev/null || true
chmod 640 /etc/ssl/private/ssl-cert-snakeoil.key 2>/dev/null || true
chown root:ssl-cert /etc/ssl/private/ssl-cert-snakeoil.key 2>/dev/null || true

mkdir -p /etc/nginx/snippets /var/lib/vzone/acme /var/lib/vzone/ssl /var/lib/vzone/nginx/domains

install_stub() {
  local path="$1"
  local name="$2"
  if [[ -f "$path" ]] && grep -q 'fastcgi_pass' "$path" 2>/dev/null; then
    echo "[vzone] Conservation snippet ${name}"
    return
  fi
  if [[ "$name" == "phpmyadmin" ]]; then
    cat > "$path" <<'EOF'
location = /phpmyadmin { return 302 /phpmyadmin/; }
location /phpmyadmin/ {
    default_type text/plain;
    return 503 "phpMyAdmin non installé.\n";
}
EOF
  else
    cat > "$path" <<'EOF'
location = /webmail { return 302 /webmail/; }
location /webmail/ {
    default_type text/plain;
    return 503 "Roundcube non installé.\n";
}
EOF
  fi
}

install_stub /etc/nginx/snippets/vzone-phpmyadmin.inc phpmyadmin
install_stub /etc/nginx/snippets/vzone-roundcube.inc roundcube

DOMAINS_DIR="${VZONE_NGINX_DOMAINS_DIR:-/var/lib/vzone/nginx/domains}"
chown -R vzone:vzone /var/lib/vzone/nginx /var/lib/vzone/acme 2>/dev/null || true
chmod 755 "$DOMAINS_DIR" /var/lib/vzone/acme
chmod -R a+rX /var/lib/vzone/acme

SSL_DIR="/var/lib/vzone/ssl/${PANEL_PRIMARY}"
if [[ -d /var/lib/vzone/ssl ]]; then
  chown -R vzone:www-data /var/lib/vzone/ssl
  find /var/lib/vzone/ssl -type d -exec chmod 750 {} \; 2>/dev/null || true
  find /var/lib/vzone/ssl -type f -name '*.pem' -exec chmod 640 {} \; 2>/dev/null || true
fi

cat > /etc/nginx/conf.d/vzone-map-upgrade.conf <<'EOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
EOF
cat > /etc/nginx/conf.d/vzone-domains-include.conf <<EOF
include ${DOMAINS_DIR}/*.conf;
EOF
[[ -f "${DOMAINS_DIR}/.keep.conf" ]] || echo "# placeholder" > "${DOMAINS_DIR}/.keep.conf"

CERT="/etc/ssl/certs/ssl-cert-snakeoil.pem"
KEY="/etc/ssl/private/ssl-cert-snakeoil.key"
if [[ -n "$PANEL_PRIMARY" && -f "${SSL_DIR}/fullchain.pem" && -f "${SSL_DIR}/privkey.pem" ]]; then
  CERT="${SSL_DIR}/fullchain.pem"
  KEY="${SSL_DIR}/privkey.pem"
  echo "[vzone] HTTPS panel: Let's Encrypt (${PANEL_PRIMARY})"
else
  echo "[vzone] HTTPS panel: snakeoil (en attendant Let's Encrypt)"
fi

# Vérifier lisibilité par www-data
if ! sudo -u www-data test -r "$CERT" 2>/dev/null; then
  echo "[vzone] ALERTE: www-data ne lit pas $CERT — correction droits"
  chmod a+r "$CERT" 2>/dev/null || true
fi
if ! sudo -u www-data test -r "$KEY" 2>/dev/null; then
  echo "[vzone] ALERTE: www-data ne lit pas $KEY — correction droits"
  chown root:ssl-cert "$KEY" 2>/dev/null || true
  chmod 640 "$KEY" 2>/dev/null || true
  usermod -aG ssl-cert www-data 2>/dev/null || true
fi

TMP="$(mktemp)"
export TMP PANEL_NAMES CERT KEY
cp "$SRC" "$TMP"
python3 - <<'PY'
import os
from pathlib import Path
tmp = Path(os.environ["TMP"])
text = tmp.read_text(encoding="utf-8")
text = text.replace("__PANEL_SERVER_NAMES__", os.environ["PANEL_NAMES"])
text = text.replace("__SSL_CERTIFICATE__", os.environ["CERT"])
text = text.replace("__SSL_CERTIFICATE_KEY__", os.environ["KEY"])
for token in ("__PANEL_SERVER_NAMES__", "__SSL_CERTIFICATE__", "__SSL_CERTIFICATE_KEY__"):
    if token in text:
        raise SystemExit(f"placeholder non remplacé: {token}")
tmp.write_text(text, encoding="utf-8")
print("[vzone] conf panel assemblée")
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
chmod a+x /opt /opt/vzone /opt/vzone/frontend "${VZONE_ROOT}/frontend/dist" 2>/dev/null || true

for h in ${PANEL_HOSTS}; do
  [[ -n "$h" ]] || continue
  safe="$(echo "$h" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]/_/g')"
  rm -f "${DOMAINS_DIR}/${safe}.conf" 2>/dev/null || true
done

nginx -t
# restart (pas seulement reload) pour prendre en compte le nouveau groupe ssl-cert de www-data
systemctl restart nginx

sleep 1
echo "[vzone] Tests locaux"
for url in "http://127.0.0.1/login" "https://127.0.0.1/login"; do
  code="$(curl -sk -o /dev/null -w "%{http_code}" "$url" || true)"
  echo "  $url → HTTP ${code}"
done
if [[ -n "$HOST_IP" ]]; then
  code="$(curl -sk -o /dev/null -w "%{http_code}" -H "Host: ${HOST_IP}" "http://127.0.0.1/login" || true)"
  echo "  Host ${HOST_IP}/login → HTTP ${code}"
fi
echo "[vzone] Nginx OK — panel accessible via IP, hostname et HTTPS"
