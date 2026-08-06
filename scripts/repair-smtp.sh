#!/usr/bin/env bash
# Rétablit SMTP Roundcube — coupe TOUS les milters (DKIM ne peut plus casser l'envoi).
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
RC_CFG="${RC_ROOT}/config/config.inc.php"

echo "=== repair-smtp (0.32.18) — SMTP prioritaire, milters OFF ==="

strip_milters() {
  postconf -e "smtpd_milters="
  postconf -e "non_smtpd_milters="
  postconf -e "milter_default_action=accept"
  postconf -e "milter_protocol=6"
  postconf -e "milter_connect_timeout=5s"
  postconf -e "milter_command_timeout=10s"
  if [[ -f /etc/postfix/master.cf ]]; then
    # Vider toute valeur smtpd_milters=... et retirer ORIGINATING
    sed -i -E 's/^([ \t]*-o[ \t]+smtpd_milters=).*/\1/' /etc/postfix/master.cf
    sed -i '/milter_macro_daemon_name=ORIGINATING/d' /etc/postfix/master.cf
  fi
}

strip_milters

mkdir -p "$MAPS_DIR"
for f in valiases virtual_mailboxes vdomains; do
  touch "${MAPS_DIR}/${f}"; postmap "${MAPS_DIR}/${f}" 2>/dev/null || true
done

[[ -f /etc/ssl/certs/ssl-cert-snakeoil.pem ]] || {
  apt-get install -y -qq ssl-cert 2>/dev/null || true
  make-ssl-cert generate-default-snakeoil --force-overwrite 2>/dev/null || true
}

install -m 644 "${REPO_DIR}/deploy/postfix/main.cf" /etc/postfix/main.cf
sed -i "s|__HOSTNAME__|${HOSTNAME_FQDN}|g; s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/postfix/main.cf
install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf

postconf -e "compatibility_level=2"
postconf -e "mynetworks=127.0.0.0/8 [::1]/128"
postconf -e "inet_interfaces=all"
postconf -e "inet_protocols=ipv4"
postconf -e "smtpd_tls_security_level=may"
postconf -e "smtpd_tls_cert_file=/etc/ssl/certs/ssl-cert-snakeoil.pem"
postconf -e "smtpd_tls_key_file=/etc/ssl/private/ssl-cert-snakeoil.key"
strip_milters

systemctl stop postfix 2>/dev/null || true
pkill -x master 2>/dev/null || true
sleep 1
systemctl start postfix
systemctl restart dovecot 2>/dev/null || true

[[ -f "${REPO_DIR}/scripts/repair-roundcube.sh" ]] && bash "${REPO_DIR}/scripts/repair-roundcube.sh" || true
if [[ -f "$RC_CFG" ]] && php -l "$RC_CFG" >/dev/null 2>&1; then
  sed -i "s|\$config\['smtp_host'\] = '.*'|\$config['smtp_host'] = 'tls://127.0.0.1:587'|" "$RC_CFG" 2>/dev/null || true
  sed -i "s|\$config\['smtp_user'\] = '.*'|\$config['smtp_user'] = '%u'|" "$RC_CFG" 2>/dev/null || true
  sed -i "s|\$config\['smtp_pass'\] = '.*'|\$config['smtp_pass'] = '%p'|" "$RC_CFG" 2>/dev/null || true
fi
systemctl restart php8.1-fpm 2>/dev/null || systemctl restart php8.2-fpm 2>/dev/null || systemctl restart php8.3-fpm 2>/dev/null || true

# Garde anti-régression (timer 1 min)
install_smtp_guard() {
  local unit_dir=/etc/systemd/system
  install -m 755 "${REPO_DIR}/scripts/vzone-smtp-guard.sh" /usr/local/sbin/vzone-smtp-guard 2>/dev/null \
    || install -m 755 "${REPO_DIR}/scripts/vzone-smtp-guard.sh" "${REPO_DIR}/scripts/vzone-smtp-guard.sh"
  # Service pointe vers /opt/vzone-src (lien habituel) ou REPO_DIR
  sed "s|/opt/vzone-src|${REPO_DIR}|g" \
    "${REPO_DIR}/deploy/systemd/vzone-smtp-guard.service" > "${unit_dir}/vzone-smtp-guard.service"
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-smtp-guard.timer" "${unit_dir}/vzone-smtp-guard.timer"
  systemctl daemon-reload
  systemctl enable --now vzone-smtp-guard.timer 2>/dev/null || true
}
install_smtp_guard

echo "postfix=$(systemctl is-active postfix) milters_main='$(postconf -h smtpd_milters)'"
echo "master milters:"
grep -n 'smtpd_milters' /etc/postfix/master.cf || true
echo "=== Déconnexion Roundcube + Ctrl+F5 + envoi ==="
echo "DKIM optionnel (ne casse plus SMTP): sudo bash ${REPO_DIR}/scripts/repair-dkim.sh"
echo "=== repair-smtp OK ==="
