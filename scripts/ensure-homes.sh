#!/usr/bin/env bash
# Assure un répertoire homes writable par l'utilisateur système vzone.
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_USER="${VZONE_USER:-vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
DEFAULT_DATA="${VZONE_DATA:-/var/lib/vzone}"
TARGET_HOME="${DEFAULT_DATA}/homes"

if [[ -f "$ENV_FILE" ]]; then
  # Migrer l'ancien /home (non writable par vzone) vers data/homes
  if grep -qE '^VZONE_HOME_ROOT=/home/?$' "$ENV_FILE"; then
    echo "[vzone] Migration VZONE_HOME_ROOT → ${TARGET_HOME}"
    sed -i "s|^VZONE_HOME_ROOT=.*|VZONE_HOME_ROOT=${TARGET_HOME}|" "$ENV_FILE"
  fi
  if ! grep -q '^VZONE_HOME_ROOT=' "$ENV_FILE"; then
    echo "VZONE_HOME_ROOT=${TARGET_HOME}" >> "$ENV_FILE"
  fi
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
  TARGET_HOME="${VZONE_HOME_ROOT:-$TARGET_HOME}"
fi

mkdir -p "${TARGET_HOME}/admin"/{public_html,mail,tmp,logs}
# Prépare un home type hébergement pour admin
chown -R "${VZONE_USER}:${VZONE_USER}" "${TARGET_HOME}"
chmod 755 "${TARGET_HOME}"
find "${TARGET_HOME}" -type d -exec chmod 755 {} \;

echo "[vzone] Homes OK → ${TARGET_HOME} (owner ${VZONE_USER})"
