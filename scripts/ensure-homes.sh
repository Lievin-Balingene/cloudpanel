#!/usr/bin/env bash
# Assure la racine homes (style cPanel : /home/<username>/).
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_USER="${VZONE_USER:-vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
TARGET_HOME="/home"

if [[ -f "$ENV_FILE" ]]; then
  if ! grep -q '^VZONE_HOME_ROOT=' "$ENV_FILE"; then
    echo "VZONE_HOME_ROOT=/home" >> "$ENV_FILE"
  fi
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
  TARGET_HOME="${VZONE_HOME_ROOT:-/home}"
fi

ensure_cpanel_home() {
  local home="$1"
  mkdir -p "${home}"/{public_html/cgi-bin,mail,tmp,logs,etc,ssl,.trash}
  if [[ ! -e "${home}/www" ]]; then
    ln -sfn public_html "${home}/www"
  fi
}

mkdir -p "${TARGET_HOME}"

# Le processus panel (vzone) doit pouvoir créer /home/<user>
if command -v setfacl >/dev/null 2>&1; then
  setfacl -m "u:${VZONE_USER}:rwx" "${TARGET_HOME}" || true
  setfacl -d -m "u:${VZONE_USER}:rwx" "${TARGET_HOME}" || true
fi
chgrp "${VZONE_USER}" "${TARGET_HOME}" 2>/dev/null || true
chmod 775 "${TARGET_HOME}" 2>/dev/null || true

ensure_cpanel_home "${TARGET_HOME}/admin"
chown -R "${VZONE_USER}:${VZONE_USER}" "${TARGET_HOME}/admin"

if getent group vmail >/dev/null 2>&1; then
  usermod -aG vmail "${VZONE_USER}" 2>/dev/null || true
  find "${TARGET_HOME}" -mindepth 2 -maxdepth 2 -type d -name mail \
    -exec chmod 2770 {} \; -exec chgrp vmail {} \; 2>/dev/null || true
fi

echo "[vzone] Homes cPanel OK → ${TARGET_HOME}/<username> (créateur ${VZONE_USER})"
