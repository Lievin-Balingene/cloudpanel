#!/usr/bin/env bash
# Force le site V-zone comme seul vhost HTTP (désactive la page welcome nginx).
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
SRC="${1:-${VZONE_ROOT}/deploy/nginx/vzone.conf}"

[[ -f "$SRC" ]] || { echo "Config introuvable: $SRC"; exit 1; }

# Snippet phpMyAdmin : stub si pas encore installé (évite nginx -t en échec)
mkdir -p /etc/nginx/snippets
if [[ ! -f /etc/nginx/snippets/vzone-phpmyadmin.inc ]]; then
  cat > /etc/nginx/snippets/vzone-phpmyadmin.inc <<'EOF'
# phpMyAdmin non installé — exécutez: sudo bash scripts/install-phpmyadmin.sh
location = /phpmyadmin {
    return 302 /phpmyadmin/;
}
location /phpmyadmin/ {
    default_type text/plain;
    return 503 "phpMyAdmin n'est pas encore installé. Exécutez: sudo bash /opt/vzone-src/scripts/install-phpmyadmin.sh\n";
}
EOF
fi

# Vhosts domaines clients (écrits par le panel)
DOMAINS_DIR="${VZONE_NGINX_DOMAINS_DIR:-/var/lib/vzone/nginx/domains}"
mkdir -p "$DOMAINS_DIR" /var/lib/vzone/acme
chown -R vzone:vzone /var/lib/vzone/nginx /var/lib/vzone/acme 2>/dev/null || true
chmod 755 "$DOMAINS_DIR"
# Map WebSocket pour proxy apps
cat > /etc/nginx/conf.d/vzone-map-upgrade.conf <<'EOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
EOF
# Include des vhosts domaines (http context)
cat > /etc/nginx/conf.d/vzone-domains-include.conf <<EOF
include ${DOMAINS_DIR}/*.conf;
EOF
# Fichier placeholder pour éviter erreur include si vide
if [[ ! -f "${DOMAINS_DIR}/.keep.conf" ]]; then
  echo "# vzone domains placeholder" > "${DOMAINS_DIR}/.keep.conf"
fi

# Retirer TOUS les sites default / welcome
rm -f /etc/nginx/sites-enabled/default \
      /etc/nginx/sites-enabled/default.bak \
      /etc/nginx/sites-enabled/000-default \
      /etc/nginx/conf.d/default.conf 2>/dev/null || true

if [[ -d /etc/nginx/sites-available ]]; then
  install -m 644 "$SRC" /etc/nginx/sites-available/vzone
  ln -sfn /etc/nginx/sites-available/vzone /etc/nginx/sites-enabled/vzone
  # Désactiver tout autre enabled qui pourrait prendre default_server
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
  install -m 644 "$SRC" /etc/nginx/conf.d/vzone.conf
fi

# Droits lecture dist pour www-data
if [[ ! -f "${VZONE_ROOT}/frontend/dist/index.html" ]]; then
  echo "[vzone] ERREUR: ${VZONE_ROOT}/frontend/dist/index.html manquant (build frontend requis)"
  exit 1
fi
chmod -R a+rX "${VZONE_ROOT}/frontend" || true
# Traversée /opt/vzone pour www-data
chmod a+x /opt /opt/vzone /opt/vzone/frontend 2>/dev/null || true

nginx -t
systemctl reload nginx || systemctl restart nginx
sleep 1
echo "[vzone] Nginx OK — site V-zone actif"
code="$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/login || true)"
echo "[vzone] GET /login → HTTP ${code}"
if [[ "$code" != "200" ]]; then
  echo "[vzone] Diagnostic sites-enabled:"
  ls -la /etc/nginx/sites-enabled/ 2>/dev/null || true
  echo "[vzone] root actifs:"
  nginx -T 2>/dev/null | grep -E "^\s*root |default_server" || true
  exit 1
fi
