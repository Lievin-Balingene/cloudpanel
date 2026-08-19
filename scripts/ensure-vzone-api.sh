#!/usr/bin/env bash
# Garantit vzone-api (Daphne) sur 127.0.0.1:8000.
# Tue les gunicorn/orphelins qui bloquent le port (cause fréquente après install/update).
# Usage: sudo bash scripts/ensure-vzone-api.sh
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${VZONE_ENV:-/etc/vzone/vzone.env}"

port8000_line() {
  ss -lntp 2>/dev/null | grep -E '127\.0\.0\.1:8000|127\.0\.0\.1:8000 ' | head -n1 || true
}

port8000_busy() {
  ss -lntp 2>/dev/null | grep -qE ':8000\s'
}

api_listener_is_daphne() {
  local line
  line="$(port8000_line)"
  [[ -n "$line" ]] || return 1
  if echo "$line" | grep -qiE 'gunicorn|uvicorn'; then
    return 1
  fi
  echo "$line" | grep -qi 'daphne' || return 1
  systemctl is-active --quiet vzone-api 2>/dev/null
}

free_port_8000() {
  echo "[vzone-api] Libération port 8000…"
  systemctl stop vzone-api 2>/dev/null || true
  sleep 1

  # Orphelins panel (ancienne stack gunicorn sur :8000)
  pkill -f 'gunicorn.*vzone\.asgi' 2>/dev/null || true
  pkill -f 'gunicorn.*vzone\.wsgi' 2>/dev/null || true
  pkill -f 'gunicorn.*vzone\.settings' 2>/dev/null || true
  pkill -f '/opt/vzone/backend.*gunicorn' 2>/dev/null || true
  pkill -f 'daphne.*vzone\.asgi' 2>/dev/null || true
  sleep 1

  if port8000_busy; then
    echo "[vzone-api] Port 8000 encore occupé : $(port8000_line)"
    if command -v fuser >/dev/null 2>&1; then
      fuser -k 8000/tcp 2>/dev/null || true
      sleep 1
    fi
  fi

  if port8000_busy; then
    echo "[vzone-api] ERREUR: impossible de libérer le port 8000" >&2
    ss -lntp 2>/dev/null | grep ':8000' >&2 || true
    return 1
  fi
  echo "[vzone-api] Port 8000 libre"
}

start_vzone_api() {
  if [[ ! -x "${VZONE_ROOT}/backend/.venv/bin/daphne" ]]; then
    echo "[vzone-api] ERREUR: daphne absent — lancez install.sh ou update.sh" >&2
    return 1
  fi
  systemctl daemon-reload
  systemctl enable vzone-api 2>/dev/null || true
  systemctl start vzone-api
}

wait_api_ready() {
  local i code
  for i in $(seq 1 30); do
    if port8000_busy && api_listener_is_daphne; then
      code="$(curl -s -o /dev/null -w '%{http_code}' -m 2 \
        -X POST "http://127.0.0.1:8000/api/v1/auth/login/" \
        -H "Content-Type: application/json" \
        -d '{}' 2>/dev/null || echo 000)"
      if [[ "$code" =~ ^[2345] ]]; then
        echo "[vzone-api] API Daphne OK (127.0.0.1:8000, login HTTP ${code})"
        return 0
      fi
    fi
    sleep 1
  done
  return 1
}

echo "=== ensure-vzone-api ==="

systemctl start postgresql 2>/dev/null || true
systemctl start redis-server 2>/dev/null || systemctl start redis 2>/dev/null || true

if api_listener_is_daphne; then
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 2 \
    -X POST "http://127.0.0.1:8000/api/v1/auth/login/" \
    -H "Content-Type: application/json" \
    -d '{}' 2>/dev/null || echo 000)"
  if [[ "$code" =~ ^[2345] ]]; then
    echo "[vzone-api] Déjà OK — Daphne actif (login HTTP ${code})"
    exit 0
  fi
  echo "[vzone-api] Daphne écoute mais API ne répond pas — redémarrage"
fi

if port8000_busy && ! api_listener_is_daphne; then
  echo "[vzone-api] ALERTE: mauvais processus sur :8000 ($(port8000_line))"
fi

free_port_8000
start_vzone_api

if wait_api_ready; then
  echo "=== ensure-vzone-api OK ==="
  exit 0
fi

echo "[vzone-api] ERREUR: vzone-api indisponible après démarrage" >&2
systemctl --no-pager -l status vzone-api | head -n 30 >&2 || true
journalctl -u vzone-api -n 40 --no-pager >&2 || true
exit 1
