#!/usr/bin/env bash
# Répare Postfix submission (Roundcube « SMTP service unavailable »).
# Usage: sudo bash /opt/vzone-src/scripts/repair-smtp.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
[[ -f "$ENV_FILE" ]] && { set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a; }

MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-/var/lib/vzone/mail/maps}"
HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"

echo "=== repair-smtp ==="

mkdir -p "$MAPS_DIR/dkim"
touch "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" \
  "${MAPS_DIR}/valiases" "${MAPS_DIR}/virtual_mailboxes" "${MAPS_DIR}/vdomains"
chgrp opendkim "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true
chmod 640 "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true

# Postfix main + master (sans chroot — milter/SASL fiables)
if [[ -f "${REPO_DIR}/deploy/postfix/main.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/main.cf" /etc/postfix/main.cf
  sed -i "s|__HOSTNAME__|${HOSTNAME_FQDN}|g" /etc/postfix/main.cf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/postfix/main.cf
fi
if [[ -f "${REPO_DIR}/deploy/postfix/master.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
fi

# OpenDKIM → maps panel
if [[ -f "${REPO_DIR}/deploy/opendkim/opendkim.conf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/opendkim/opendkim.conf" /etc/opendkim.conf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/opendkim.conf
fi
if [[ -f "${REPO_DIR}/deploy/opendkim/TrustedHosts" ]]; then
  install -m 644 "${REPO_DIR}/deploy/opendkim/TrustedHosts" /etc/opendkim/TrustedHosts
  grep -qxF "127.0.0.1" /etc/opendkim/TrustedHosts || echo "127.0.0.1" >> /etc/opendkim/TrustedHosts
  grep -qxF "localhost" /etc/opendkim/TrustedHosts || echo "localhost" >> /etc/opendkim/TrustedHosts
fi

postmap "${MAPS_DIR}/valiases" 2>/dev/null || true
postmap "${MAPS_DIR}/virtual_mailboxes" 2>/dev/null || true
postmap "${MAPS_DIR}/vdomains" 2>/dev/null || true

# Agent reload
if [[ -f "${REPO_DIR}/scripts/vzone-mail-reload.sh" ]]; then
  install -m 755 "${REPO_DIR}/scripts/vzone-mail-reload.sh" /usr/local/sbin/vzone-mail-reload
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-mail-reload.service" /etc/systemd/system/vzone-mail-reload.service
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-mail-reload.path" /etc/systemd/system/vzone-mail-reload.path
  systemctl daemon-reload
  systemctl enable --now vzone-mail-reload.path 2>/dev/null || true
fi

echo "[check] postfix…"
postfix check 2>&1 || true

systemctl enable --now opendkim 2>/dev/null || true
systemctl restart opendkim 2>/dev/null || true
systemctl enable --now postfix 2>/dev/null || true
systemctl restart postfix 2>/dev/null || true
systemctl reload dovecot 2>/dev/null || true

sleep 1
echo
echo "[status]"
systemctl is-active postfix opendkim dovecot 2>/dev/null || true
ss -lntp 2>/dev/null | grep -E ':25|:587|:465|:8891' || netstat -lntp 2>/dev/null | grep -E ':25|:587|:465|:8891' || true

echo
echo "[test local submission]"
if command -v timeout >/dev/null 2>&1; then
  timeout 3 bash -c 'echo QUIT | openssl s_client -connect 127.0.0.1:587 -starttls smtp 2>/dev/null' \
    | head -n 5 || echo "(openssl test skip)"
fi

echo
echo "=== Si Roundcube échoue encore ==="
echo "  journalctl -u postfix -u opendkim -n 40 --no-pager"
echo "  doveadm auth test user@domaine 'motdepasse'"
echo "=== repair-smtp OK ==="
