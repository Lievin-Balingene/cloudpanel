#!/usr/bin/env bash
# Désinstallation propre de V-zone Panel
set -euo pipefail

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
VZONE_DATA="${VZONE_DATA:-/var/lib/vzone}"
VZONE_LOG="${VZONE_LOG:-/var/log/vzone}"
PURGE_DATA=0

for arg in "$@"; do
  case "$arg" in
    --purge) PURGE_DATA=1 ;;
  esac
done

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

systemctl stop vzone-api vzone-worker vzone-beat 2>/dev/null || true
systemctl disable vzone-api vzone-worker vzone-beat 2>/dev/null || true
rm -f /etc/systemd/system/vzone-*.service
systemctl daemon-reload

rm -f /etc/nginx/sites-enabled/vzone /etc/nginx/sites-available/vzone /etc/nginx/conf.d/vzone.conf
systemctl reload nginx 2>/dev/null || true

rm -rf "$VZONE_ROOT"
rm -rf /etc/vzone

if [[ "$PURGE_DATA" -eq 1 ]]; then
  rm -rf "$VZONE_DATA" "$VZONE_LOG"
  if id vzone >/dev/null 2>&1; then
    userdel vzone || true
  fi
  echo "[vzone] Données et utilisateur système purgés."
else
  echo "[vzone] Données conservées dans ${VZONE_DATA} (utilisez --purge pour tout supprimer)."
fi

echo "[vzone] Désinstallation terminée."
