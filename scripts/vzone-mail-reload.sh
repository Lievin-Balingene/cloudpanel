#!/usr/bin/env bash
# Sync maps OpenDKIM + permissions + reload Postfix/Dovecot/OpenDKIM (root).
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }

FLAG="${VZONE_MAIL_RELOAD_FLAG:-/var/lib/vzone/mail/maps/reload.requested}"
rm -f "$FLAG" 2>/dev/null || true

ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
[[ -f "$ENV_FILE" ]] && { set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a; }

MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-/var/lib/vzone/mail/maps}"
mkdir -p "${MAPS_DIR}/dkim"

# Permissions clés DKIM (opendkim doit lire)
if [[ -d "${MAPS_DIR}/dkim" ]]; then
  chgrp -R opendkim "${MAPS_DIR}/dkim" 2>/dev/null || true
  chmod -R g+rX "${MAPS_DIR}/dkim" 2>/dev/null || true
  find "${MAPS_DIR}/dkim" -type f -name '*.private' -exec chmod 640 {} \; 2>/dev/null || true
fi

for f in opendkim-KeyTable opendkim-SigningTable; do
  if [[ -f "${MAPS_DIR}/${f}" ]]; then
    chgrp opendkim "${MAPS_DIR}/${f}" 2>/dev/null || true
    chmod 640 "${MAPS_DIR}/${f}" 2>/dev/null || true
    # Miroir legacy /etc (si conf ancienne pointe encore ici)
    if [[ -d /etc/opendkim ]]; then
      cp -f "${MAPS_DIR}/${f}" "/etc/opendkim/${f#opendkim-}" 2>/dev/null || true
      chown opendkim:opendkim "/etc/opendkim/${f#opendkim-}" 2>/dev/null || true
      chmod 640 "/etc/opendkim/${f#opendkim-}" 2>/dev/null || true
    fi
  fi
done

# postmap virtual maps
for name in valiases virtual_mailboxes vdomains; do
  if [[ -f "${MAPS_DIR}/${name}" ]] && command -v postmap >/dev/null 2>&1; then
    postmap "${MAPS_DIR}/${name}" 2>/dev/null || true
  fi
done

systemctl reload opendkim 2>/dev/null || systemctl restart opendkim 2>/dev/null || true
systemctl reload dovecot 2>/dev/null || true
systemctl reload postfix 2>/dev/null || true

echo "[vzone] mail maps + OpenDKIM rechargés (${MAPS_DIR})"
