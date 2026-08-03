#!/usr/bin/env bash
# Répare HTTPS : sync vhosts + ouvre 443 + reload nginx.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"

echo "[vzone] Réparation HTTPS / vhosts SSL"

if command -v ufw >/dev/null 2>&1; then
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
  ufw status | head -n 20 || true
elif command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-service=http || true
  firewall-cmd --permanent --add-service=https || true
  firewall-cmd --reload || true
fi

if [[ -f "$ENV_FILE" ]]; then
  set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a
fi

export DJANGO_SETTINGS_MODULE=vzone.settings.production
PY="${VZONE_ROOT}/backend/.venv/bin/python"
if [[ -x "$PY" ]]; then
  cd "${VZONE_ROOT}/backend"
  "$PY" manage.py shell <<'PY'
from apps.domains.vhosts import sync_all_domain_vhosts
n = sync_all_domain_vhosts()
print(f"vhosts synced: {n}")
PY
fi

nginx -t
systemctl reload nginx || systemctl restart nginx

echo "[vzone] Ports en écoute :"
ss -lntup | grep -E ':80|:443' || netstat -lntup 2>/dev/null | grep -E ':80|:443' || true

echo "[vzone] Test local :"
curl -sI -o /dev/null -w "HTTP  http://127.0.0.1/ → %{http_code}\n" http://127.0.0.1/ || true
curl -skI -o /dev/null -w "HTTPS https://127.0.0.1/ → %{http_code}\n" https://127.0.0.1/ || true

DOMAIN="${1:-vpanel.vzonecloud.co.uk}"
if [[ -n "$DOMAIN" ]]; then
  echo "[vzone] Test Host ${DOMAIN}:"
  curl -sI -o /dev/null -w "HTTP  → %{http_code}\n" -H "Host: ${DOMAIN}" http://127.0.0.1/ || true
  curl -skI -o /dev/null -w "HTTPS → %{http_code}\n" --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}/" || true
  ls -la "/var/lib/vzone/ssl/${DOMAIN}/" 2>/dev/null || echo "Pas de PEM pour ${DOMAIN}"
  ls -la "/var/lib/vzone/nginx/domains/"*"${DOMAIN}"* 2>/dev/null || ls /var/lib/vzone/nginx/domains/ 2>/dev/null || true
fi

echo "[vzone] ensure-https terminé"
