#!/usr/bin/env bash
# Sauvegarde locale de la configuration et de la base V-zone
set -euo pipefail

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
VZONE_DATA="${VZONE_DATA:-/var/lib/vzone}"
BACKUP_DIR="${1:-/var/backups/vzone}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/vzone-${STAMP}"

mkdir -p "$TARGET"
# shellcheck disable=SC1091
source /etc/vzone/vzone.env

pg_dump -h "$VZONE_DB_HOST" -U "$VZONE_DB_USER" -d "$VZONE_DB_NAME" -Fc \
  > "${TARGET}/database.dump"
cp -a /etc/vzone "${TARGET}/etc-vzone"
tar -C "$VZONE_DATA" -czf "${TARGET}/data.tar.gz" . 2>/dev/null || true
tar -C "$VZONE_ROOT" -czf "${TARGET}/app.tar.gz" \
  --exclude='backend/.venv' --exclude='frontend/node_modules' . 

echo "[vzone] Sauvegarde créée: ${TARGET}"
