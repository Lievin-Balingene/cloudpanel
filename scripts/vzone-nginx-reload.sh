#!/usr/bin/env bash
# Reload Nginx après validation (root).
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }

FLAG="${VZONE_NGINX_RELOAD_FLAG:-/var/lib/vzone/nginx/reload.requested}"
rm -f "$FLAG" 2>/dev/null || true

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx introuvable" >&2
  exit 1
fi

nginx -t
systemctl reload nginx || systemctl restart nginx
echo "[vzone] nginx rechargé"
