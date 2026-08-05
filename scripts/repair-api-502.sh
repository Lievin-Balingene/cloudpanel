#!/usr/bin/env bash
# Répare le 502 Bad Gateway (nginx → Daphne 127.0.0.1:8000).
# Usage: sudo bash /opt/vzone-src/scripts/repair-api-502.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${VZONE_ENV:-/etc/vzone/vzone.env}"

echo "=== repair-api-502 ==="

echo "[1] État services"
systemctl is-active vzone-api nginx postgresql redis-server 2>/dev/null \
  || systemctl is-active vzone-api nginx postgresql redis 2>/dev/null \
  || true
ss -lntp 2>/dev/null | grep -E ':8000|:80 |:443 ' || true

echo "[2] Logs API (40 dernières lignes)"
journalctl -u vzone-api -n 40 --no-pager 2>/dev/null || true

echo "[3] Dépendances"
systemctl start postgresql 2>/dev/null || true
systemctl start redis-server 2>/dev/null || systemctl start redis 2>/dev/null || true

if [[ ! -x "${VZONE_ROOT}/backend/.venv/bin/daphne" ]]; then
  echo "Daphne manquant dans ${VZONE_ROOT}/backend/.venv — lancez update.sh" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

echo "[4] Redémarrage vzone-api"
systemctl daemon-reload
systemctl enable vzone-api 2>/dev/null || true
systemctl restart vzone-api

echo "[5] Attente écoute :8000"
ok=0
for i in $(seq 1 30); do
  if ss -lntp 2>/dev/null | grep -q ':8000'; then
    if curl -sf -o /dev/null -m 2 "http://127.0.0.1:8000/api/v1/" \
      || curl -sf -o /dev/null -m 2 "http://127.0.0.1:8000/api/v1/auth/me/" \
      || curl -s -o /dev/null -m 2 -w "%{http_code}" "http://127.0.0.1:8000/api/v1/" | grep -qE '^[2345]'; then
      ok=1
      echo "  API up après ${i}s"
      break
    fi
  fi
  sleep 1
done

if [[ "${ok}" -ne 1 ]]; then
  echo "[ERREUR] API toujours inaccessible sur 127.0.0.1:8000" >&2
  systemctl --no-pager -l status vzone-api | head -n 40 >&2 || true
  journalctl -u vzone-api -n 60 --no-pager >&2 || true
  exit 1
fi

echo "[6] Reload nginx (sans restart)"
if command -v nginx >/dev/null 2>&1; then
  nginx -t && systemctl reload nginx || systemctl restart nginx
fi

echo "[7] Test proxy login"
code="$(curl -sk -o /dev/null -w "%{http_code}" "http://127.0.0.1/api/v1/" || true)"
echo "  /api/v1/ → HTTP ${code}"
login_code="$(curl -sk -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1/api/v1/auth/login/" \
  -H "Content-Type: application/json" -d '{}' || true)"
echo "  POST /auth/login/ → HTTP ${login_code} (400/401 attendu si API vivante ; 502 = encore cassé)"

if [[ "${login_code}" == "502" || "${login_code}" == "000" ]]; then
  echo "[ERREUR] nginx renvoie encore 502 vers l'API" >&2
  exit 1
fi

echo "=== OK — réessayez le login dans le navigateur ==="
