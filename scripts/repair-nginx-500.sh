#!/usr/bin/env bash
# Répare immédiatement le 500 nginx + accès IP au panel.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"

echo "=== repair-nginx-500 ==="
tail -n 40 /var/log/nginx/error.log 2>/dev/null || true
echo "---"
bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf"
systemctl is-active vzone-api nginx || true
curl -skI http://127.0.0.1/login | head -n 8 || true
curl -skI https://127.0.0.1/login | head -n 8 || true
IP="$(hostname -I | awk '{print $1}')"
echo "Ouvrez: http://${IP}/login  et  https://vpanel.vzonecloud.co.uk/login"
echo "=== done ==="
