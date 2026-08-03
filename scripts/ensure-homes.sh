#!/usr/bin/env bash
# Assure la racine homes style cPanel : /home/<username>/
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_USER="${VZONE_USER:-vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Si ancien chemin encore configuré → migration complète
if [[ -f "$ENV_FILE" ]] && grep -qE '^VZONE_HOME_ROOT=/(var/lib/vzone/homes|home/vzone)(/homes)?/?$' "$ENV_FILE"; then
  echo "[vzone] Ancien VZONE_HOME_ROOT détecté — migration cPanel…"
  bash "${SCRIPT_DIR}/migrate-homes-cpanel.sh"
  exit 0
fi

# Si /var/lib/vzone/homes contient encore des comptes alors que env dit /home
if [[ -d /var/lib/vzone/homes ]] && [[ -n "$(ls -A /var/lib/vzone/homes 2>/dev/null || true)" ]]; then
  echo "[vzone] Comptes trouvés sous /var/lib/vzone/homes — migration cPanel…"
  bash "${SCRIPT_DIR}/migrate-homes-cpanel.sh"
  exit 0
fi

TARGET_HOME="/home"
if [[ -f "$ENV_FILE" ]]; then
  if ! grep -q '^VZONE_HOME_ROOT=' "$ENV_FILE"; then
    echo "VZONE_HOME_ROOT=/home" >> "$ENV_FILE"
  else
    # Normalise toute valeur vers /home (cPanel)
    sed -i 's|^VZONE_HOME_ROOT=.*|VZONE_HOME_ROOT=/home|' "$ENV_FILE"
  fi
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
  TARGET_HOME="${VZONE_HOME_ROOT:-/home}"
fi

ensure_cpanel_home() {
  local home="$1"
  mkdir -p "${home}"/{public_html/cgi-bin,mail,tmp,logs,etc,ssl,.trash,domains}
  if [[ ! -e "${home}/www" ]]; then
    ln -sfn public_html "${home}/www"
  fi
  chmod 755 "${home}" "${home}"/public_html 2>/dev/null || true
}

mkdir -p "${TARGET_HOME}"

if command -v setfacl >/dev/null 2>&1; then
  setfacl -m "u:${VZONE_USER}:rwx" "${TARGET_HOME}" || true
  setfacl -d -m "u:${VZONE_USER}:rwx" "${TARGET_HOME}" || true
fi

ensure_cpanel_home "${TARGET_HOME}/admin"
chown -R "${VZONE_USER}:${VZONE_USER}" "${TARGET_HOME}/admin"

if getent group vmail >/dev/null 2>&1; then
  usermod -aG vmail "${VZONE_USER}" 2>/dev/null || true
fi

echo "[vzone] Homes cPanel OK → ${TARGET_HOME}/<username>"
ls -la "${TARGET_HOME}" 2>/dev/null | head -n 30 || true
