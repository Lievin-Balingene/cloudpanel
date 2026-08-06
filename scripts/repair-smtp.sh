#!/usr/bin/env bash
# Répare Postfix + Roundcube (« SMTP service unavailable »).
# Usage: sudo bash /opt/vzone-src/scripts/repair-smtp.sh
set -uo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
[[ -f "$ENV_FILE" ]] && { set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a; }

MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-/var/lib/vzone/mail/maps}"
HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-/opt/vzone/roundcube}"

echo "=== repair-smtp ==="

mkdir -p "$MAPS_DIR/dkim"
touch "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" \
  "${MAPS_DIR}/valiases" "${MAPS_DIR}/virtual_mailboxes" "${MAPS_DIR}/vdomains"
chgrp opendkim "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true
chmod 640 "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true

# Postfix main + master (sans chroot, sans postlog — compatible Ubuntu 20.04)
if [[ -f "${REPO_DIR}/deploy/postfix/main.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/main.cf" /etc/postfix/main.cf
  sed -i "s|__HOSTNAME__|${HOSTNAME_FQDN}|g" /etc/postfix/main.cf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/postfix/main.cf
fi
if [[ -f "${REPO_DIR}/deploy/postfix/master.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
fi
# Nettoyer une éventuelle ligne postlog incompatible
sed -i '/^postlog[[:space:]]/d' /etc/postfix/master.cf 2>/dev/null || true

# OpenDKIM
if [[ -f "${REPO_DIR}/deploy/opendkim/opendkim.conf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/opendkim/opendkim.conf" /etc/opendkim.conf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/opendkim.conf
fi
if [[ -f "${REPO_DIR}/deploy/opendkim/TrustedHosts" ]]; then
  install -m 644 "${REPO_DIR}/deploy/opendkim/TrustedHosts" /etc/opendkim/TrustedHosts
  grep -qxF "127.0.0.1" /etc/opendkim/TrustedHosts || echo "127.0.0.1" >> /etc/opendkim/TrustedHosts
  grep -qxF "localhost" /etc/opendkim/TrustedHosts || echo "localhost" >> /etc/opendkim/TrustedHosts
  grep -qxF "::1" /etc/opendkim/TrustedHosts || echo "::1" >> /etc/opendkim/TrustedHosts
fi

postmap "${MAPS_DIR}/valiases" 2>/dev/null || true
postmap "${MAPS_DIR}/virtual_mailboxes" 2>/dev/null || true
postmap "${MAPS_DIR}/vdomains" 2>/dev/null || true

# Roundcube → SMTP local :25 (mynetworks, sans TLS)
RC_CFG="${RC_ROOT}/config/config.inc.php"
if [[ -f "$RC_CFG" ]]; then
  echo "[roundcube] smtp → 127.0.0.1:25 (sans auth)"
  sed -i "s|\$config\['smtp_host'\] = '.*'|\$config['smtp_host'] = '127.0.0.1:25'|" "$RC_CFG" || true
  if grep -q "smtp_user" "$RC_CFG"; then
    sed -i "s|\$config\['smtp_user'\] = '.*'|\$config['smtp_user'] = ''|" "$RC_CFG" || true
  else
    echo "\$config['smtp_user'] = '';" >> "$RC_CFG"
  fi
  if grep -q "smtp_pass" "$RC_CFG"; then
    sed -i "s|\$config\['smtp_pass'\] = '.*'|\$config['smtp_pass'] = ''|" "$RC_CFG" || true
  else
    echo "\$config['smtp_pass'] = '';" >> "$RC_CFG"
  fi
fi

# Agent reload
if [[ -f "${REPO_DIR}/scripts/vzone-mail-reload.sh" ]]; then
  install -m 755 "${REPO_DIR}/scripts/vzone-mail-reload.sh" /usr/local/sbin/vzone-mail-reload
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-mail-reload.service" /etc/systemd/system/vzone-mail-reload.service
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-mail-reload.path" /etc/systemd/system/vzone-mail-reload.path
  systemctl daemon-reload
  systemctl enable --now vzone-mail-reload.path 2>/dev/null || true
fi

echo "[check] postfix…"
if ! postfix check 2>&1; then
  echo "ERREUR: postfix check a échoué" >&2
fi

systemctl enable opendkim postfix dovecot 2>/dev/null || true
systemctl restart opendkim 2>/dev/null || true
systemctl stop postfix 2>/dev/null || true
systemctl start postfix 2>/dev/null || true
systemctl reload dovecot 2>/dev/null || systemctl restart dovecot 2>/dev/null || true

sleep 1
echo
echo "[status]"
systemctl is-active postfix || { echo "postfix INACTIF"; journalctl -u postfix -n 30 --no-pager || true; }
systemctl is-active opendkim dovecot 2>/dev/null || true
ss -lntp 2>/dev/null | grep -E ':25 |:587 |:465 |:8891' || true

echo
echo "[test SMTP :25]"
if command -v timeout >/dev/null 2>&1; then
  timeout 3 bash -c 'exec 3<>/dev/tcp/127.0.0.1/25; echo -e "EHLO localhost\r\nQUIT\r\n" >&3; cat <&3' 2>/dev/null | head -n 8 \
    || echo "Port 25 injoignable"
fi

echo
echo "=== repair-smtp OK — réessayez Roundcube ==="
echo "  Logs: journalctl -u postfix -n 40 --no-pager"
