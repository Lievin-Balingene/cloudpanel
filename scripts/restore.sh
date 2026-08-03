#!/usr/bin/env bash
# Restauration depuis une sauvegarde produite par backup.sh
set -euo pipefail

BACKUP_PATH="${1:-}"
[[ -n "$BACKUP_PATH" && -d "$BACKUP_PATH" ]] || {
  echo "Usage: sudo bash scripts/restore.sh /var/backups/vzone/vzone-TIMESTAMP"
  exit 1
}

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
VZONE_DATA="${VZONE_DATA:-/var/lib/vzone}"

systemctl stop vzone-api vzone-worker vzone-beat || true
# shellcheck disable=SC1091
source "${BACKUP_PATH}/etc-vzone/vzone.env"
cp -a "${BACKUP_PATH}/etc-vzone/." /etc/vzone/
pg_restore -h "$VZONE_DB_HOST" -U "$VZONE_DB_USER" -d "$VZONE_DB_NAME" --clean --if-exists \
  "${BACKUP_PATH}/database.dump" || true
if [[ -f "${BACKUP_PATH}/data.tar.gz" ]]; then
  mkdir -p "$VZONE_DATA"
  tar -C "$VZONE_DATA" -xzf "${BACKUP_PATH}/data.tar.gz"
fi
systemctl start vzone-api vzone-worker vzone-beat
echo "[vzone] Restauration terminée depuis ${BACKUP_PATH}"
