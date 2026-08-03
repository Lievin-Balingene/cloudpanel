#!/usr/bin/env bash
# Force le site V-zone comme seul vhost HTTP (désactive la page welcome nginx).
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
SRC="${1:-${VZONE_ROOT}/deploy/nginx/vzone.conf}"

[[ -f "$SRC" ]] || { echo "Config introuvable: $SRC"; exit 1; }

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
