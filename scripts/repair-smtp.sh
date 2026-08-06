#!/usr/bin/env bash
# Urgence SMTP : coupe milters globaux + restaure submission (sans DKIM d'abord).
# Usage: sudo bash /opt/vzone-src/scripts/repair-smtp.sh
# Puis si envoi OK: sudo bash /opt/vzone-src/scripts/repair-dkim.sh
set -uo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
[[ -f "$ENV_FILE" ]] && { set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a; }

MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-/var/lib/vzone/mail/maps}"
HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-/opt/vzone/roundcube}"
RC_CFG="${RC_ROOT}/config/config.inc.php"

echo "=== repair-smtp URGENCE (0.32.14) ==="

# Couper milters globaux immédiatement
postconf -e "smtpd_milters="
postconf -e "non_smtpd_milters="
postconf -e "milter_default_action=accept"

mkdir -p "$MAPS_DIR"
for f in valiases virtual_mailboxes vdomains; do
  touch "${MAPS_DIR}/${f}"; postmap "${MAPS_DIR}/${f}" 2>/dev/null || true
done

[[ -f /etc/ssl/certs/ssl-cert-snakeoil.pem ]] || {
  apt-get install -y -qq ssl-cert 2>/dev/null || true
  make-ssl-cert generate-default-snakeoil --force-overwrite 2>/dev/null || true
}

# master.cf SANS milter d'abord (SMTP sûr)
cat > /etc/postfix/master.cf <<'EOF'
smtp      inet  n       -       n       -       -       smtpd
  -o smtpd_tls_security_level=may
  -o smtpd_milters=
  -o milter_default_action=accept

submission inet n       -       n       -       -       smtpd
  -o syslog_name=postfix/submission
  -o smtpd_tls_security_level=encrypt
  -o smtpd_sasl_auth_enable=yes
  -o smtpd_sasl_type=dovecot
  -o smtpd_sasl_path=private/auth
  -o smtpd_tls_auth_only=yes
  -o smtpd_reject_unlisted_recipient=no
  -o smtpd_client_restrictions=permit_mynetworks,permit_sasl_authenticated,reject
  -o smtpd_relay_restrictions=permit_mynetworks,permit_sasl_authenticated,reject
  -o smtpd_sender_restrictions=permit_mynetworks,permit_sasl_authenticated,reject
  -o smtpd_recipient_restrictions=permit_mynetworks,permit_sasl_authenticated,reject_unauth_destination
  -o smtpd_milters=
  -o milter_default_action=accept

smtps     inet  n       -       n       -       -       smtpd
  -o syslog_name=postfix/smtps
  -o smtpd_tls_wrappermode=yes
  -o smtpd_sasl_auth_enable=yes
  -o smtpd_sasl_type=dovecot
  -o smtpd_sasl_path=private/auth
  -o smtpd_client_restrictions=permit_mynetworks,permit_sasl_authenticated,reject
  -o smtpd_relay_restrictions=permit_mynetworks,permit_sasl_authenticated,reject
  -o smtpd_sender_restrictions=permit_mynetworks,permit_sasl_authenticated,reject
  -o smtpd_recipient_restrictions=permit_mynetworks,permit_sasl_authenticated,reject_unauth_destination
  -o smtpd_milters=
  -o milter_default_action=accept

pickup    unix  n       -       n       60      1       pickup
cleanup   unix  n       -       n       -       0       cleanup
qmgr      unix  n       -       n       300     1       qmgr
tlsmgr    unix  -       -       n       1000?   1       tlsmgr
rewrite   unix  -       -       n       -       -       trivial-rewrite
bounce    unix  -       -       n       -       0       bounce
defer     unix  -       -       n       -       0       bounce
trace     unix  -       -       n       -       0       bounce
verify    unix  -       -       n       -       1       verify
flush     unix  n       -       n       1000?   0       flush
proxymap  unix  -       -       n       -       -       proxymap
proxywrite unix -       -       n       -       1       proxymap
smtp      unix  -       -       n       -       -       smtp
relay     unix  -       -       n       -       -       smtp
showq     unix  n       -       n       -       -       showq
error     unix  -       -       n       -       -       error
retry     unix  -       -       n       -       -       error
discard   unix  -       -       n       -       -       discard
local     unix  -       n       n       -       -       local
virtual   unix  -       n       n       -       -       virtual
lmtp      unix  -       -       n       -       -       lmtp
anvil     unix  -       -       n       -       1       anvil
scache    unix  -       -       n       -       1       scache
EOF

if [[ -f "${REPO_DIR}/deploy/postfix/main.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/main.cf" /etc/postfix/main.cf
  sed -i "s|__HOSTNAME__|${HOSTNAME_FQDN}|g" /etc/postfix/main.cf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/postfix/main.cf
fi

postconf -e "compatibility_level=2"
postconf -e "mynetworks=127.0.0.0/8 [::1]/128"
postconf -e "inet_interfaces=all"
postconf -e "inet_protocols=ipv4"
postconf -e "smtpd_tls_security_level=may"
postconf -e "smtpd_tls_cert_file=/etc/ssl/certs/ssl-cert-snakeoil.pem"
postconf -e "smtpd_tls_key_file=/etc/ssl/private/ssl-cert-snakeoil.key"
postconf -e "smtpd_milters="
postconf -e "non_smtpd_milters="
postconf -e "milter_default_action=accept"

systemctl stop postfix 2>/dev/null || true
pkill -x master 2>/dev/null || true
sleep 1
systemctl start postfix
systemctl restart dovecot 2>/dev/null || true

if [[ -f "${REPO_DIR}/scripts/repair-roundcube.sh" ]]; then
  bash "${REPO_DIR}/scripts/repair-roundcube.sh" || true
fi
if [[ -f "$RC_CFG" ]] && php -l "$RC_CFG" >/dev/null 2>&1; then
  sed -i "s|\$config\['smtp_host'\] = '.*'|\$config['smtp_host'] = 'tls://127.0.0.1:587'|" "$RC_CFG" 2>/dev/null || true
  sed -i "s|\$config\['smtp_user'\] = '.*'|\$config['smtp_user'] = '%u'|" "$RC_CFG" 2>/dev/null || true
  sed -i "s|\$config\['smtp_pass'\] = '.*'|\$config['smtp_pass'] = '%p'|" "$RC_CFG" 2>/dev/null || true
fi
systemctl restart php8.1-fpm 2>/dev/null || systemctl restart php8.2-fpm 2>/dev/null || systemctl restart php8.3-fpm 2>/dev/null || true

echo
echo "postfix=$(systemctl is-active postfix) milters='$(postconf -h smtpd_milters)'"
ss -lntp | grep ':587 ' || true
echo
echo "SMTP rétabli SANS DKIM."
echo "1) Déconnexion Roundcube + Ctrl+F5 + envoi test"
echo "2) Si OK: sudo bash ${REPO_DIR}/scripts/repair-dkim.sh"
echo "=== OK ==="
