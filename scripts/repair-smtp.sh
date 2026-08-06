#!/usr/bin/env bash
# Répare l'envoi Roundcube (SMTP unavailable → sendmail/PHP mail).
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

echo "=== repair-smtp (0.32.9) ==="

mkdir -p "$MAPS_DIR/dkim"
for f in opendkim-KeyTable opendkim-SigningTable valiases virtual_mailboxes vdomains; do
  touch "${MAPS_DIR}/${f}"
done
postmap "${MAPS_DIR}/valiases" 2>/dev/null || true
postmap "${MAPS_DIR}/virtual_mailboxes" 2>/dev/null || true
postmap "${MAPS_DIR}/vdomains" 2>/dev/null || true

if [[ ! -f /etc/ssl/certs/ssl-cert-snakeoil.pem ]]; then
  apt-get install -y -qq ssl-cert 2>/dev/null || true
  make-ssl-cert generate-default-snakeoil --force-overwrite 2>/dev/null || true
fi

# Postfix conf
if [[ -f "${REPO_DIR}/deploy/postfix/main.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/main.cf" /etc/postfix/main.cf
  sed -i "s|__HOSTNAME__|${HOSTNAME_FQDN}|g" /etc/postfix/main.cf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/postfix/main.cf
fi
if [[ -f "${REPO_DIR}/deploy/postfix/master.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
fi
sed -i '/^postlog[[:space:]]/d' /etc/postfix/master.cf 2>/dev/null || true
sed -i '/smtpd_milters=/d' /etc/postfix/master.cf 2>/dev/null || true

postconf -e "compatibility_level=2" 2>/dev/null || true
postconf -e "mynetworks=127.0.0.0/8 [::1]/128" 2>/dev/null || true
postconf -e "inet_interfaces=all" 2>/dev/null || true
postconf -e "inet_protocols=ipv4" 2>/dev/null || true
postconf -e "smtpd_milters=" 2>/dev/null || true
postconf -e "non_smtpd_milters=" 2>/dev/null || true
postconf -e "milter_default_action=accept" 2>/dev/null || true
# sendmail compatible (PHP mail())
postconf -e "mailbox_size_limit=0" 2>/dev/null || true

if ! postfix check >/tmp/vzone-postfix-check.txt 2>&1; then
  echo "[warn] postfix check KO"
  cat /tmp/vzone-postfix-check.txt || true
  if [[ -f /usr/share/postfix/master.cf.dist ]]; then
    cp -a /usr/share/postfix/master.cf.dist /etc/postfix/master.cf
  fi
fi

# OpenDKIM (optionnel)
if [[ -f "${REPO_DIR}/deploy/opendkim/opendkim.conf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/opendkim/opendkim.conf" /etc/opendkim.conf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/opendkim.conf
fi

# --- Roundcube : smtp_host vide = PHP mail() / sendmail ---
RC_CFG="${RC_ROOT}/config/config.inc.php"
if [[ -f "$RC_CFG" ]]; then
  echo "[roundcube] smtp_host='' (PHP mail / sendmail)"
  cp -a "$RC_CFG" "${RC_CFG}.bak.$(date +%s)" 2>/dev/null || true
  sed -i "/\$config\['smtp_host'\]/d" "$RC_CFG"
  sed -i "/\$config\['smtp_user'\]/d" "$RC_CFG"
  sed -i "/\$config\['smtp_pass'\]/d" "$RC_CFG"
  sed -i "/\$config\['smtp_port'\]/d" "$RC_CFG"
  sed -i "/\$config\['smtp_server'\]/d" "$RC_CFG"
  sed -i "/\$config\['smtp_helo_host'\]/d" "$RC_CFG"
  # Bloc unique en fin de fichier
  cat >> "$RC_CFG" <<'PHP'

// V-zone repair-smtp 0.32.9 — envoi via sendmail (pas de socket SMTP)
$config['smtp_host'] = '';
$config['smtp_user'] = '';
$config['smtp_pass'] = '';
PHP
  grep -n "smtp_host" "$RC_CFG" || true
else
  echo "[ERREUR] Config Roundcube introuvable: $RC_CFG"
fi

# sendmail doit pointer vers postfix
if [[ -x /usr/sbin/sendmail ]]; then
  echo "sendmail: $(readlink -f /usr/sbin/sendmail 2>/dev/null || echo /usr/sbin/sendmail)"
fi
# php.ini sendmail_path
for ini in /etc/php/*/fpm/php.ini /etc/php/*/cli/php.ini; do
  [[ -f "$ini" ]] || continue
  if grep -qE '^;?sendmail_path' "$ini"; then
    sed -i 's|^;?sendmail_path.*|sendmail_path = /usr/sbin/sendmail -t -i|' "$ini" 2>/dev/null \
      || sed -i 's|^sendmail_path.*|sendmail_path = /usr/sbin/sendmail -t -i|' "$ini" || true
  else
    echo 'sendmail_path = /usr/sbin/sendmail -t -i' >> "$ini"
  fi
done

systemctl reload php*-fpm 2>/dev/null || systemctl restart php8.1-fpm 2>/dev/null || systemctl restart php8.3-fpm 2>/dev/null || true
systemctl restart php8.1-fpm 2>/dev/null || systemctl restart php8.2-fpm 2>/dev/null || systemctl restart php8.3-fpm 2>/dev/null || true

echo "[postfix] restart…"
systemctl enable postfix dovecot 2>/dev/null || true
systemctl stop postfix 2>/dev/null || true
pkill -x master 2>/dev/null || true
sleep 1
systemctl start postfix 2>/dev/null || postfix start 2>/dev/null || true
systemctl restart dovecot 2>/dev/null || true
systemctl restart opendkim 2>/dev/null || true

sleep 1
echo
echo "===== DIAGNOSTIC ====="
systemctl is-active postfix dovecot 2>/dev/null || true
ss -lntp 2>/dev/null | grep -E ':25 |:587 ' || true
echo "smtp_host in config:"
grep -n "smtp_host" "${RC_CFG}" 2>/dev/null | tail -n 5 || true

echo
echo "===== TEST sendmail ====="
if echo -e "Subject: vzone-smtp-test\nFrom: root@${HOSTNAME_FQDN}\nTo: root\n\nrepair-smtp test\n" \
  | /usr/sbin/sendmail -t -i 2>/tmp/vzone-sendmail.err; then
  echo "sendmail: OK"
  mailq 2>/dev/null | head -n 15 || true
else
  echo "sendmail: FAIL"
  cat /tmp/vzone-sendmail.err || true
fi

echo
echo "===== Roundcube errors (si présent) ====="
tail -n 30 "${RC_ROOT}/logs/errors.log" 2>/dev/null || echo "(pas de errors.log)"

echo
echo "=== IMPORTANT ==="
echo "1) Déconnectez-vous de Roundcube puis reconnectez-vous (session)"
echo "2) Ctrl+F5 sur /webmail/"
echo "3) Renvoyez un mail"
echo "Si échec, collez: tail -n 50 ${RC_ROOT}/logs/errors.log"
echo "=== repair-smtp OK ==="
