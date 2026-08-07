#!/usr/bin/env bash
# Installe Nginx V-zone :
# - :80/:443 IP = Access Denied
# - hostnames panel = SPA
# - ports Admin 9086 / Client 9082 / Webmail 9095
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# Hostnames panel UNIQUEMENT (pas l'IP publique → Access Denied sur IP:80)
# localhost pour admin local. Ports dédiés acceptent l'IP.
PANEL_HOSTS="${VZONE_PANEL_HOSTNAMES:-}"
PANEL_HOSTS="${PANEL_HOSTS//,/ }"
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
PANEL_NAMES="localhost 127.0.0.1"
[[ -n "$PANEL_HOSTS" ]] && PANEL_NAMES="${PANEL_NAMES} ${PANEL_HOSTS}"
PANEL_NAMES="$(echo "$PANEL_NAMES" | xargs)"
PANEL_PRIMARY="$(echo "$PANEL_HOSTS" | awk '{print $1}')"

ADMIN_PORT="${VZONE_ADMIN_PORT:-9086}"
CLIENT_PORT="${VZONE_CLIENT_PORT:-9082}"
WEBMAIL_PORT="${VZONE_WEBMAIL_PORT:-9095}"

echo "[vzone] Panel hostnames (80/443): ${PANEL_NAMES}"
echo "[vzone] Ports: Admin=${ADMIN_PORT} Client=${CLIENT_PORT} Webmail=${WEBMAIL_PORT}"

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

mkdir -p /etc/nginx/snippets /var/lib/vzone/acme /var/lib/vzone/ssl /var/lib/vzone/nginx/domains /var/lib/vzone/suspended

# Page « Account Suspended » (style cPanel) pour les domaines des comptes suspendus
SUSPENDED_SRC=""
for candidate in \
  "${SCRIPT_DIR}/../deploy/nginx/suspended/index.html" \
  "${VZONE_ROOT}/deploy/nginx/suspended/index.html"; do
  if [[ -f "$candidate" ]]; then
    SUSPENDED_SRC="$candidate"
    break
  fi
done
if [[ -n "$SUSPENDED_SRC" ]]; then
  cp -a "$SUSPENDED_SRC" /var/lib/vzone/suspended/index.html
  chmod 644 /var/lib/vzone/suspended/index.html
  chmod 755 /var/lib/vzone/suspended
  echo "[vzone] Page suspension installée → /var/lib/vzone/suspended/index.html"
else
  cat > /var/lib/vzone/suspended/index.html <<'HTML'
<!DOCTYPE html><html><head><meta charset="utf-8"><title>Account Suspended</title></head>
<body style="font-family:system-ui;padding:2rem;text-align:center">
<h1>This Account Has Been Suspended</h1>
<p>Contact your hosting provider.</p>
<p lang="fr">Ce compte a été suspendu. Contactez votre hébergeur.</p>
</body></html>
HTML
  chmod 644 /var/lib/vzone/suspended/index.html
fi

# Page Access Denied (IP nue :80/:443) — style « SORRY! » cPanel
DENIED_SRC=""
for candidate in \
  "${SCRIPT_DIR}/../deploy/nginx/access-denied.html" \
  "${VZONE_ROOT}/deploy/nginx/access-denied.html"; do
  [[ -f "$candidate" ]] && DENIED_SRC="$candidate" && break
done
mkdir -p /var/lib/vzone/nginx
SERVER_HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname 2>/dev/null || echo server.vzonecloud.com)"
SERVER_HOSTNAME_FQDN="${PANEL_PRIMARY:-$SERVER_HOSTNAME_FQDN}"
WEBMASTER_EMAIL="${VZONE_WEBMASTER_EMAIL:-webmaster@${SERVER_HOSTNAME_FQDN}}"
COPYRIGHT_YEAR="$(date +%Y)"
if [[ -n "$DENIED_SRC" ]]; then
  sed \
    -e "s|__WEBMASTER_EMAIL__|${WEBMASTER_EMAIL}|g" \
    -e "s|__SERVER_HOSTNAME__|${SERVER_HOSTNAME_FQDN}|g" \
    -e "s|__COPYRIGHT_YEAR__|${COPYRIGHT_YEAR}|g" \
    "$DENIED_SRC" > /var/lib/vzone/nginx/access-denied.html
  chmod 644 /var/lib/vzone/nginx/access-denied.html
  echo "[vzone] Page Access Denied (SORRY!) → webmaster=${WEBMASTER_EMAIL}"
else
  echo '<!DOCTYPE html><html><head><meta charset="utf-8"><title>SORRY!</title></head><body><h1>SORRY!</h1></body></html>' \
    > /var/lib/vzone/nginx/access-denied.html
  chmod 644 /var/lib/vzone/nginx/access-denied.html
fi

# Snippet locations panel SPA
PANEL_APP_SRC=""
for candidate in \
  "${SCRIPT_DIR}/../deploy/nginx/panel-app.inc" \
  "${VZONE_ROOT}/deploy/nginx/panel-app.inc"; do
  [[ -f "$candidate" ]] && PANEL_APP_SRC="$candidate" && break
done
if [[ -n "$PANEL_APP_SRC" ]]; then
  install -m 644 "$PANEL_APP_SRC" /etc/nginx/snippets/vzone-panel-app.inc
fi

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

# Une seule source de vérité : conf.d (toujours inclus par nginx Debian/Ubuntu).
# Les installs précédentes mettaient parfois la conf seulement dans sites-enabled
# alors que conf.d était vide → 404 sur toutes les pages.
install -m 644 "$TMP" /etc/nginx/conf.d/zz-vzone-panel.conf
rm -f /etc/nginx/conf.d/vzone.conf \
      /etc/nginx/sites-enabled/vzone \
      /etc/nginx/sites-available/vzone 2>/dev/null || true

# Ports dédiés Admin / Client / Webmail
PORTS_SRC=""
for candidate in \
  "${SCRIPT_DIR}/../deploy/nginx/vzone-ports.conf" \
  "${VZONE_ROOT}/deploy/nginx/vzone-ports.conf"; do
  [[ -f "$candidate" ]] && PORTS_SRC="$candidate" && break
done
if [[ -n "$PORTS_SRC" ]]; then
  # Hostname Django pour domaine:9082 style cPanel (n'importe quel Host → panel)
  BACKEND_HOST="${PANEL_PRIMARY:-}"
  if [[ -z "$BACKEND_HOST" ]]; then
    BACKEND_HOST="$(hostname -f 2>/dev/null || true)"
  fi
  if [[ -z "$BACKEND_HOST" || "$BACKEND_HOST" == "localhost" ]]; then
    BACKEND_HOST="${HOST_IP:-localhost}"
  fi
  # Toujours dans ALLOWED_HOSTS
  if [[ -f "$ENV_FILE" ]]; then
    CURRENT_AH="$(grep '^VZONE_ALLOWED_HOSTS=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)"
    if [[ -n "$BACKEND_HOST" && "$CURRENT_AH" != *"$BACKEND_HOST"* ]]; then
      if grep -q '^VZONE_ALLOWED_HOSTS=' "$ENV_FILE"; then
        sed -i "s|^VZONE_ALLOWED_HOSTS=.*|VZONE_ALLOWED_HOSTS=${CURRENT_AH},${BACKEND_HOST}|" "$ENV_FILE"
      else
        echo "VZONE_ALLOWED_HOSTS=${BACKEND_HOST},localhost,127.0.0.1" >> "$ENV_FILE"
      fi
    fi
  fi
  PORTS_TMP="$(mktemp)"
  sed -e "s/__VZONE_ADMIN_PORT__/${ADMIN_PORT}/g" \
      -e "s/__VZONE_CLIENT_PORT__/${CLIENT_PORT}/g" \
      -e "s/__VZONE_WEBMAIL_PORT__/${WEBMAIL_PORT}/g" \
      -e "s/__PANEL_BACKEND_HOST__/${BACKEND_HOST}/g" \
      "$PORTS_SRC" > "$PORTS_TMP"
  if grep -q '__PANEL_BACKEND_HOST__' "$PORTS_TMP"; then
    echo "[vzone] ERREUR: placeholder PANEL_BACKEND_HOST non remplacé" >&2
    rm -f "$PORTS_TMP"
    exit 1
  fi
  install -m 644 "$PORTS_TMP" /etc/nginx/conf.d/zz-vzone-ports.conf
  rm -f "$PORTS_TMP"
  echo "[vzone] Ports installés → zz-vzone-ports.conf (backend Host=${BACKEND_HOST})"
fi

# Firewall ports panel
if command -v ufw >/dev/null 2>&1; then
  ufw allow "${ADMIN_PORT}/tcp" comment "vzone-admin" 2>/dev/null || ufw allow "${ADMIN_PORT}/tcp" || true
  ufw allow "${CLIENT_PORT}/tcp" comment "vzone-client" 2>/dev/null || ufw allow "${CLIENT_PORT}/tcp" || true
  ufw allow "${WEBMAIL_PORT}/tcp" comment "vzone-webmail" 2>/dev/null || ufw allow "${WEBMAIL_PORT}/tcp" || true
fi

# Persister ports dans env
if [[ -f "$ENV_FILE" ]]; then
  for kv in \
    "VZONE_ADMIN_PORT=${ADMIN_PORT}" \
    "VZONE_CLIENT_PORT=${CLIENT_PORT}" \
    "VZONE_WEBMAIL_PORT=${WEBMAIL_PORT}"; do
    key="${kv%%=*}"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
      sed -i "s|^${key}=.*|${kv}|" "$ENV_FILE"
    else
      echo "$kv" >> "$ENV_FILE"
    fi
  done
fi

# Désactiver tout autre default_server concurrent
for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
  [[ -e "$f" ]] || continue
  base="$(basename "$f")"
  [[ "$base" == "zz-vzone-panel.conf" ]] && continue
  [[ "$base" == "zz-vzone-ports.conf" ]] && continue
  [[ "$base" == "vzone-domains-include.conf" ]] && continue
  [[ "$base" == "vzone-map-upgrade.conf" ]] && continue
  if grep -q "default_server" "$f" 2>/dev/null; then
    echo "[vzone] Désactivation default_server concurrent: $f"
    if [[ -d /etc/nginx/sites-enabled && "$f" == /etc/nginx/sites-enabled/* ]]; then
      rm -f "$f"
    else
      mv -f "$f" "${f}.disabled-by-vzone" 2>/dev/null || rm -f "$f"
    fi
  fi
done
rm -f "$TMP"

# Retirer vhosts domaine qui dupliquent le panel (conflit server_name)
for h in ${PANEL_HOSTS}; do
  [[ -n "$h" ]] || continue
  safe="$(echo "$h" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]/_/g')"
  rm -f "${DOMAINS_DIR}/${safe}.conf" 2>/dev/null || true
done
# IP / localhost seulement — PAS le FQDN machine (peut être un domaine client)
for h in ${HOST_IP} localhost 127.0.0.1; do
  [[ -n "$h" ]] || continue
  safe="$(echo "$h" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]/_/g')"
  rm -f "${DOMAINS_DIR}/${safe}.conf" 2>/dev/null || true
done
if [[ -d "$DOMAINS_DIR" ]]; then
  for f in "${DOMAINS_DIR}"/*.conf; do
    [[ -f "$f" ]] || continue
    [[ "$(basename "$f")" == ".keep.conf" ]] && continue
    for h in ${PANEL_HOSTS} ${HOST_IP} localhost; do
      [[ -n "$h" ]] || continue
      if grep -qE "server_name[^;]*[[:space:]]${h}([[:space:;]]|$)" "$f" 2>/dev/null; then
        echo "[vzone] Suppression conflit $f ($h)"
        rm -f "$f"
      fi
    done
    # default_server dans un vhost domaine = casse le panel
    if grep -q "default_server" "$f" 2>/dev/null; then
      echo "[vzone] Suppression vhost domaine default_server: $f"
      rm -f "$f"
    fi
  done
fi

if [[ ! -f "${VZONE_ROOT}/frontend/dist/index.html" ]]; then
  SRC_FE=""
  for candidate in /opt/vzone-src/frontend "${VZONE_ROOT}/../vzone-src/frontend"; do
    [[ -f "${candidate}/package.json" ]] && SRC_FE="$candidate" && break
  done
  if [[ -n "$SRC_FE" ]]; then
    echo "[vzone] dist manquant — build frontend depuis ${SRC_FE}"
    mkdir -p "${VZONE_ROOT}/frontend"
    rsync -a --delete --exclude node_modules --exclude dist "${SRC_FE}/" "${VZONE_ROOT}/frontend/"
    cd "${VZONE_ROOT}/frontend"
    npm ci || npm install
    npm run build
  fi
fi
if [[ ! -f "${VZONE_ROOT}/frontend/dist/index.html" ]]; then
  echo "[vzone] ERREUR: ${VZONE_ROOT}/frontend/dist/index.html manquant"
  echo "[vzone] Exécutez: sudo bash /opt/vzone-src/scripts/repair-frontend.sh"
  exit 1
fi

# www-data doit pouvoir traverser /opt → … → dist
chmod a+x /opt /opt/vzone /opt/vzone/frontend "${VZONE_ROOT}/frontend/dist" 2>/dev/null || true
chmod -R a+rX "${VZONE_ROOT}/frontend/dist" || true
chown -R root:www-data "${VZONE_ROOT}/frontend/dist" 2>/dev/null || true
if ! sudo -u www-data test -r "${VZONE_ROOT}/frontend/dist/index.html" 2>/dev/null; then
  echo "[vzone] ALERTE: www-data ne lit pas index.html — chmod 755 sur les parents"
  chmod 755 /opt /opt/vzone /opt/vzone/frontend "${VZONE_ROOT}/frontend/dist" 2>/dev/null || true
  chmod 644 "${VZONE_ROOT}/frontend/dist/index.html" 2>/dev/null || true
fi

nginx -t
# Préférer reload : un restart nginx coupe /api → 502 au login.
# Restart uniquement si reload échoue, ou si VZONE_NGINX_FORCE_RESTART=1
# (ex. premier install pour prendre le groupe ssl-cert).
if [[ "${VZONE_NGINX_FORCE_RESTART:-0}" == "1" ]]; then
  systemctl restart nginx
elif [[ "${VZONE_NGINX_RELOAD_ONLY:-0}" == "1" ]] || systemctl is-active --quiet nginx; then
  systemctl reload nginx || systemctl restart nginx
else
  systemctl restart nginx
fi

sleep 1
echo "[vzone] Tests locaux"
PANEL_OK=1
# localhost → panel OK
for url in "http://127.0.0.1/login" "https://127.0.0.1/login"; do
  code="$(curl -sk -o /tmp/vzone-nginx-test.body -w "%{http_code}" "$url" || true)"
  echo "  $url → HTTP ${code}"
  if [[ "$code" != "200" ]]; then
    PANEL_OK=0
  fi
done
# IP publique sur :80 → Access Denied (403)
if [[ -n "$HOST_IP" ]]; then
  code="$(curl -sk -o /tmp/vzone-nginx-test.body -w "%{http_code}" -H "Host: ${HOST_IP}" "http://127.0.0.1/login" || true)"
  echo "  Host ${HOST_IP}/login → HTTP ${code} (attendu 403 Access Denied)"
  [[ "$code" == "403" ]] || echo "[vzone] Avertissement: IP devrait renvoyer 403" >&2
fi
# Hostname panel → OK
if [[ -n "$PANEL_PRIMARY" ]]; then
  code="$(curl -sk -o /tmp/vzone-nginx-test.body -w "%{http_code}" -H "Host: ${PANEL_PRIMARY}" "http://127.0.0.1/login" || true)"
  echo "  Host ${PANEL_PRIMARY}/login → HTTP ${code}"
  [[ "$code" == "200" ]] || PANEL_OK=0
fi
# Ports dédiés
for port in "$ADMIN_PORT" "$CLIENT_PORT" "$WEBMAIL_PORT"; do
  code="$(curl -sk -o /tmp/vzone-nginx-test.body -w "%{http_code}" "http://127.0.0.1:${port}/" || true)"
  echo "  :${port}/ → HTTP ${code}"
  if [[ "$code" != "200" && "$code" != "302" && "$code" != "301" ]]; then
    echo "[vzone] Avertissement: port ${port} ne répond pas (code ${code})" >&2
  fi
done
if [[ "${PANEL_OK}" -ne 1 ]]; then
  echo "[vzone] ERREUR: /login localhost ne renvoie pas HTTP 200" >&2
  echo "[vzone] Diagnostique:" >&2
  echo "  ls -la ${VZONE_ROOT}/frontend/dist/index.html" >&2
  echo "  nginx -T 2>/dev/null | grep -E 'default_server|root |zz-vzone|try_files' | head -40" >&2
  nginx -T 2>/dev/null | grep -E 'listen |server_name |root |default_server|try_files|zz-vzone' | head -60 >&2 || true
  echo "[vzone] Réparez: sudo bash /opt/vzone-src/scripts/repair-panel-404.sh" >&2
  exit 1
fi
echo "[vzone] Nginx OK — Admin :${ADMIN_PORT} · Client :${CLIENT_PORT} · Webmail :${WEBMAIL_PORT}"
echo "[vzone] IP:80 = Access Denied · hostname panel / localhost = OK"

# Régénérer TOUS les vhosts domaines → public_html (évite 7une.info → /login)
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" && -f "$ENV_FILE" ]]; then
  echo "[vzone] Sync vhosts domaines (sites clients)"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY' || echo "[vzone] Avertissement: sync vhosts échoué"
from apps.domains.vhosts import sync_all_domain_vhosts
n = sync_all_domain_vhosts()
print(f"[vzone] vhosts domaines régénérés: {n}")
PY
  echo "[vzone] Fichiers:"
  ls -la "${DOMAINS_DIR}" 2>/dev/null | head -n 40 || true
fi

# Synchroniser ALLOWED_HOSTS (sinon API domaines échoue via vpanel / IP)
if [[ -f "$ENV_FILE" ]]; then
  HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  NEED_HOSTS="localhost,127.0.0.1"
  [[ -n "$HOST_IP" ]] && NEED_HOSTS="${NEED_HOSTS},${HOST_IP}"
  for h in ${PANEL_HOSTS}; do
    [[ -n "$h" ]] && NEED_HOSTS="${NEED_HOSTS},${h}"
  done
  CURRENT="$(grep '^VZONE_ALLOWED_HOSTS=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)"
  MERGED="$CURRENT"
  IFS=',' read -ra PARTS <<< "$NEED_HOSTS"
  for p in "${PARTS[@]}"; do
    p="$(echo "$p" | xargs)"
    [[ -z "$p" ]] && continue
    case ",${MERGED}," in
      *",${p},"*) ;;
      *) MERGED="${MERGED},${p}" ;;
    esac
  done
  MERGED="$(echo "$MERGED" | sed 's/^,//' | sed 's/,,/,/g')"
  HOSTS_CHANGED=0
  if [[ "$CURRENT" != "$MERGED" ]]; then
    HOSTS_CHANGED=1
    if grep -q '^VZONE_ALLOWED_HOSTS=' "$ENV_FILE"; then
      sed -i "s|^VZONE_ALLOWED_HOSTS=.*|VZONE_ALLOWED_HOSTS=${MERGED}|" "$ENV_FILE"
    else
      echo "VZONE_ALLOWED_HOSTS=${MERGED}" >> "$ENV_FILE"
    fi
  fi
  if [[ -z "${VZONE_PUBLIC_IP:-}" && -n "$HOST_IP" ]]; then
    grep -q '^VZONE_PUBLIC_IP=' "$ENV_FILE" || echo "VZONE_PUBLIC_IP=${HOST_IP}" >> "$ENV_FILE"
  fi
  if [[ -z "${VZONE_MAIL_PUBLIC_IP:-}" && -n "$HOST_IP" ]]; then
    grep -q '^VZONE_MAIL_PUBLIC_IP=' "$ENV_FILE" || echo "VZONE_MAIL_PUBLIC_IP=${HOST_IP}" >> "$ENV_FILE"
  fi
  # Ne jamais tuer vzone-api pendant un job SSL (VZONE_SKIP_API_RESTART=1).
  # Sur changement ALLOWED_HOSTS : restart doux + attente :8000 (évite 502 login).
  if [[ "${VZONE_SKIP_API_RESTART:-0}" != "1" && "$HOSTS_CHANGED" -eq 1 ]]; then
    systemctl try-restart vzone-api 2>/dev/null || true
    for i in $(seq 1 20); do
      if ss -lntp 2>/dev/null | grep -q ':8000'; then
        break
      fi
      sleep 0.5
    done
  fi
  echo "[vzone] ALLOWED_HOSTS → ${MERGED}"
fi

# Garde-fou final : API doit écouter sinon login = 502
if ! ss -lntp 2>/dev/null | grep -q ':8000'; then
  echo "[vzone] ALERTE: rien sur :8000 — redémarrage vzone-api"
  systemctl restart vzone-api 2>/dev/null || true
  sleep 2
fi
if ss -lntp 2>/dev/null | grep -q ':8000'; then
  echo "[vzone] API Daphne OK (127.0.0.1:8000)"
else
  echo "[vzone] ERREUR: API absente — sudo bash /opt/vzone-src/scripts/repair-api-502.sh" >&2
fi
