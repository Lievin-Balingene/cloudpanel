#!/usr/bin/env bash
# Sync maps OpenDKIM + permissions + reload Postfix/Dovecot/OpenDKIM (root).
# Ne touche JAMAIS aux milters Postfix (SMTP prioritaire).
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }

FLAG="${VZONE_MAIL_RELOAD_FLAG:-/var/lib/vzone/mail/maps/reload.requested}"
rm -f "$FLAG" 2>/dev/null || true

ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
[[ -f "$ENV_FILE" ]] && { set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a; }

MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-/var/lib/vzone/mail/maps}"
mkdir -p "${MAPS_DIR}/dkim" /etc/opendkim/keys

# Permissions clés panel
if [[ -d "${MAPS_DIR}/dkim" ]]; then
  chgrp -R opendkim "${MAPS_DIR}/dkim" 2>/dev/null || true
  chmod -R g+rX "${MAPS_DIR}/dkim" 2>/dev/null || true
  find "${MAPS_DIR}/dkim" -type f -name '*.private' -exec chmod 640 {} \; 2>/dev/null || true
fi

# Miroir /etc/opendkim avec clés locales (chemins fiables pour le daemon)
: > /etc/opendkim/KeyTable
: > /etc/opendkim/SigningTable
if [[ -s "${MAPS_DIR}/opendkim-KeyTable" ]]; then
  while read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    key_id="$(echo "$line" | awk '{print $1}')"
    rest="$(echo "$line" | awk '{print $2}')"
    domain="$(echo "$rest" | cut -d: -f1)"
    selector="$(echo "$rest" | cut -d: -f2)"
    src="$(echo "$rest" | cut -d: -f3-)"
    [[ -f "$src" ]] || continue
    dest_dir="/etc/opendkim/keys/${domain}"
    mkdir -p "$dest_dir"
    install -m 600 -o opendkim -g opendkim "$src" "${dest_dir}/${selector}.private"
    echo "${key_id} ${domain}:${selector}:${dest_dir}/${selector}.private" >> /etc/opendkim/KeyTable
  done < "${MAPS_DIR}/opendkim-KeyTable"
fi
if [[ -s "${MAPS_DIR}/opendkim-SigningTable" ]]; then
  cp -f "${MAPS_DIR}/opendkim-SigningTable" /etc/opendkim/SigningTable
fi
chown opendkim:opendkim /etc/opendkim/KeyTable /etc/opendkim/SigningTable 2>/dev/null || true
chmod 644 /etc/opendkim/KeyTable /etc/opendkim/SigningTable 2>/dev/null || true
find /etc/opendkim/keys -type f -name '*.private' -exec chmod 600 {} \; -exec chown opendkim:opendkim {} \; 2>/dev/null || true

for name in valiases virtual_mailboxes vdomains; do
  if [[ -f "${MAPS_DIR}/${name}" ]] && command -v postmap >/dev/null 2>&1; then
    postmap "${MAPS_DIR}/${name}" 2>/dev/null || true
  fi
done

systemctl reload opendkim 2>/dev/null || systemctl restart opendkim 2>/dev/null || true
systemctl reload dovecot 2>/dev/null || true
systemctl reload postfix 2>/dev/null || true

echo "[vzone] mail maps + OpenDKIM rechargés (${MAPS_DIR}) — milters inchangés"
