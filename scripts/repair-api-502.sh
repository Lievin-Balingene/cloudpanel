#!/usr/bin/env bash
# Répare le 502 Bad Gateway (nginx → Daphne 127.0.0.1:8000).
# Usage: sudo bash /opt/vzone-src/scripts/repair-api-502.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== repair-api-502 ==="
bash "${SCRIPT_DIR}/ensure-vzone-api.sh"

echo "[6] Reload nginx (sans restart)"
if command -v nginx >/dev/null 2>&1; then
  nginx -t && systemctl reload nginx || systemctl restart nginx
fi

echo "[7] Test proxy login (port panel)"
ADMIN_PORT="${VZONE_ADMIN_PORT:-9086}"
login_code="$(curl -sk -o /dev/null -w "%{http_code}" -X POST \
  "http://127.0.0.1:${ADMIN_PORT}/api/v1/auth/login/" \
  -H "Content-Type: application/json" -d '{}' || true)"
echo "  POST :${ADMIN_PORT}/auth/login/ → HTTP ${login_code} (400/401 attendu ; 502 = encore cassé)"

if [[ "${login_code}" == "502" || "${login_code}" == "000" ]]; then
  echo "[ERREUR] nginx renvoie encore 502 vers l'API" >&2
  exit 1
fi

echo "=== OK — réessayez le login dans le navigateur ==="
