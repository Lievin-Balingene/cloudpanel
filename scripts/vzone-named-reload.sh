#!/usr/bin/env bash
# Recharge BIND après export des zones V-zone.
set -euo pipefail

FLAG="${VZONE_DNS_RELOAD_FLAG:-/var/lib/vzone/named/reload.requested}"
NAMED_DIR="${VZONE_DNS_DIR:-/var/lib/vzone/named}"

rm -f "${FLAG}" 2>/dev/null || true

# Droits : named doit lire, vzone doit écrire
chgrp -R bind "${NAMED_DIR}" 2>/dev/null || chgrp -R named "${NAMED_DIR}" 2>/dev/null || true
chmod -R g+rwX "${NAMED_DIR}" 2>/dev/null || true

if command -v named-checkconf >/dev/null 2>&1; then
  named-checkconf || {
    echo "[vzone-named-reload] named-checkconf a échoué" >&2
    exit 1
  }
fi

if command -v rndc >/dev/null 2>&1; then
  rndc reconfig 2>/dev/null || true
  rndc reload 2>/dev/null || true
fi

systemctl reload named 2>/dev/null || systemctl reload bind9 2>/dev/null || \
  systemctl restart named 2>/dev/null || systemctl restart bind9 2>/dev/null || true

echo "[vzone-named-reload] OK"
