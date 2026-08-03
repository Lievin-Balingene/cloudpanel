#!/usr/bin/env bash
# Régénère la conf panel Nginx (appelé en root après SSL panel).
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }

FLAG="${VZONE_ENSURE_NGINX_FLAG:-/var/lib/vzone/nginx/ensure-nginx.requested}"
rm -f "$FLAG" 2>/dev/null || true

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
for script in \
  /opt/vzone-src/scripts/ensure-nginx.sh \
  "${VZONE_ROOT}/scripts/ensure-nginx.sh"
do
  if [[ -f "$script" ]]; then
    bash "$script" "${VZONE_ROOT}/deploy/nginx/vzone.conf"
    exit $?
  fi
done
echo "ensure-nginx.sh introuvable" >&2
exit 1
