#!/usr/bin/env bash
# Reload / graceful restart OpenLiteSpeed (root).
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }

FLAG="${VZONE_OLS_RELOAD_FLAG:-/var/lib/vzone/ols/reload.requested}"
rm -f "$FLAG" 2>/dev/null || true

OLS_ROOT="${VZONE_OLS_ROOT:-/usr/local/lsws}"
CTRL="${OLS_ROOT}/bin/lswsctrl"

if [[ -x "${CTRL}" ]]; then
  "${CTRL}" restart
  echo "[vzone] OpenLiteSpeed redémarré (lswsctrl)"
  exit 0
fi

if systemctl restart lshttpd 2>/dev/null || systemctl restart lsws 2>/dev/null; then
  echo "[vzone] OpenLiteSpeed redémarré (systemd)"
  exit 0
fi

echo "OpenLiteSpeed introuvable" >&2
exit 1
