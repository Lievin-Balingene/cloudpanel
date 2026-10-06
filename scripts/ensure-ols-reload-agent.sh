#!/usr/bin/env bash
# Installe l'agent reload OpenLiteSpeed (root) — requis pour appliquer les vhconf WP tout de suite.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "Exécutez en root." >&2
  exit 1
fi

OLS_DIR="${VZONE_DATA_ROOT:-/var/lib/vzone}/ols"
mkdir -p "${OLS_DIR}/vhconf" "${OLS_DIR}/vhosts" "${OLS_DIR}/logs"
chmod 775 "${OLS_DIR}" "${OLS_DIR}/vhconf" "${OLS_DIR}/vhosts" 2>/dev/null || true
chown -R vzone:vzone "${OLS_DIR}" 2>/dev/null || chown -R vzone:www-data "${OLS_DIR}" 2>/dev/null || true

install -m 755 "${REPO_DIR}/scripts/vzone-ols-reload.sh" /usr/local/sbin/vzone-ols-reload
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-ols-reload.service" /etc/systemd/system/vzone-ols-reload.service
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-ols-reload.path" /etc/systemd/system/vzone-ols-reload.path
systemctl daemon-reload
systemctl enable vzone-ols-reload.path 2>/dev/null || true
systemctl start vzone-ols-reload.path 2>/dev/null || true
echo "[vzone] Agent OLS reload OK (vzone-ols-reload.path)"
