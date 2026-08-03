#!/usr/bin/env bash
# Vérification de santé des services V-zone
set -euo pipefail

FAIL=0
check() {
  local name="$1"
  shift
  if "$@"; then
    echo "[ok] $name"
  else
    echo "[fail] $name"
    FAIL=1
  fi
}

check "API HTTP" curl -fsS "http://127.0.0.1/api/v1/health/" >/dev/null
check "PostgreSQL" systemctl is-active --quiet postgresql
check "Redis" systemctl is-active --quiet redis-server || systemctl is-active --quiet redis
check "vzone-api" systemctl is-active --quiet vzone-api
check "vzone-worker" systemctl is-active --quiet vzone-worker
check "Nginx" systemctl is-active --quiet nginx

exit "$FAIL"
