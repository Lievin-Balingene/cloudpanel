#!/usr/bin/env bash
# Installe et configure Postfix + Dovecot + OpenDKIM (réputation mail).
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
VZONE_USER="${VZONE_USER:-vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

DATA_ROOT="${VZONE_DATA_ROOT:-/var/lib/vzone}"
MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-${DATA_ROOT}/mail/maps}"
HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"
PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo "[vzone] Installation stack mail (Postfix / Dovecot / OpenDKIM)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# Préconfigure Postfix en Internet Site
echo "postfix postfix/mailname string ${HOSTNAME_FQDN}" | debconf-set-selections
echo "postfix postfix/main_mailer_type string 'Internet Site'" | debconf-set-selections
apt-get install -y -qq postfix dovecot-core dovecot-imapd dovecot-pop3d dovecot-lmtpd \
  opendkim opendkim-tools ca-certificates ssl-cert

# Utilisateur virtuel vmail (UID/GID stables)
if ! id vmail >/dev/null 2>&1; then
  groupadd -g 5000 vmail
  useradd -u 5000 -g vmail -d /var/mail/vhosts -s /usr/sbin/nologin -r vmail
fi
mkdir -p /var/mail/vhosts
chown -R vmail:vmail /var/mail/vhosts
# Panel (vzone) crée les boîtes ; Dovecot (vmail) les lit/écrit
usermod -aG vmail "${VZONE_USER}" 2>/dev/null || true
chmod 2770 /var/mail/vhosts
chgrp vmail /var/mail/vhosts

mkdir -p "$MAPS_DIR" "$MAPS_DIR/dkim" /etc/opendkim/keys
touch "$MAPS_DIR/vmailbox" "$MAPS_DIR/valiases" "$MAPS_DIR/vdomains" \
  "$MAPS_DIR/dovecot-users" "$MAPS_DIR/virtual_mailboxes"
chown -R "${VZONE_USER}:vmail" "${DATA_ROOT}/mail"
chmod -R g+rwX "${DATA_ROOT}/mail"
chmod 2770 "${DATA_ROOT}/mail" "$MAPS_DIR" 2>/dev/null || true
# Clés DKIM lisibles par OpenDKIM
chgrp -R opendkim "$MAPS_DIR/dkim" 2>/dev/null || true
chmod -R g+rX "$MAPS_DIR/dkim" 2>/dev/null || true
chmod 640 "$MAPS_DIR"/dovecot-users 2>/dev/null || true
chgrp vmail "$MAPS_DIR"/dovecot-users 2>/dev/null || true
# Panel peut écrire, Dovecot/vmail lit
usermod -aG vmail "${VZONE_USER}" 2>/dev/null || true

# --- Postfix ---
install -m 644 "${REPO_DIR}/deploy/postfix/main.cf" /etc/postfix/main.cf
install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
sed -i "s|__HOSTNAME__|${HOSTNAME_FQDN}|g" /etc/postfix/main.cf
sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/postfix/main.cf
postmap "$MAPS_DIR/valiases" 2>/dev/null || true
postmap "$MAPS_DIR/virtual_mailboxes" 2>/dev/null || true

# --- Dovecot ---
install -m 644 "${REPO_DIR}/deploy/dovecot/dovecot.conf" /etc/dovecot/dovecot.conf
install -m 644 "${REPO_DIR}/deploy/dovecot/10-auth.conf" /etc/dovecot/conf.d/10-auth.conf
install -m 644 "${REPO_DIR}/deploy/dovecot/10-mail.conf" /etc/dovecot/conf.d/10-mail.conf
install -m 644 "${REPO_DIR}/deploy/dovecot/10-master.conf" /etc/dovecot/conf.d/10-master.conf
install -m 644 "${REPO_DIR}/deploy/dovecot/10-ssl.conf" /etc/dovecot/conf.d/10-ssl.conf
install -m 644 "${REPO_DIR}/deploy/dovecot/auth-passwdfile.conf.ext" /etc/dovecot/conf.d/auth-passwdfile.conf.ext
# passdb pointe vers /etc/dovecot/vzone-users (plus de __MAPS_DIR__)
sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/dovecot/conf.d/10-mail.conf
if [[ -f "${MAPS_DIR}/dovecot-users" ]]; then
  install -m 640 -o root -g vmail "${MAPS_DIR}/dovecot-users" /etc/dovecot/vzone-users
else
  touch /etc/dovecot/vzone-users
  chown root:vmail /etc/dovecot/vzone-users
  chmod 640 /etc/dovecot/vzone-users
fi

# --- OpenDKIM ---
install -m 644 "${REPO_DIR}/deploy/opendkim/opendkim.conf" /etc/opendkim.conf
install -m 644 "${REPO_DIR}/deploy/opendkim/TrustedHosts" /etc/opendkim/TrustedHosts
grep -qxF "$HOSTNAME_FQDN" /etc/opendkim/TrustedHosts || echo "$HOSTNAME_FQDN" >> /etc/opendkim/TrustedHosts
[[ -n "${PUBLIC_IP}" ]] && { grep -qxF "$PUBLIC_IP" /etc/opendkim/TrustedHosts || echo "$PUBLIC_IP" >> /etc/opendkim/TrustedHosts; }
touch /etc/opendkim/KeyTable /etc/opendkim/SigningTable
chown -R opendkim:opendkim /etc/opendkim /etc/opendkim.conf
chmod 640 /etc/opendkim/KeyTable /etc/opendkim/SigningTable
# Lien vers maps générées par le panel
ln -sfn "$MAPS_DIR/dkim" /etc/opendkim/keys/vzone
if [[ -f "$MAPS_DIR/opendkim-KeyTable" ]]; then
  cp -f "$MAPS_DIR/opendkim-KeyTable" /etc/opendkim/KeyTable
  cp -f "$MAPS_DIR/opendkim-SigningTable" /etc/opendkim/SigningTable
  chown opendkim:opendkim /etc/opendkim/KeyTable /etc/opendkim/SigningTable
fi

# Socket milter
mkdir -p /var/spool/postfix/opendkim
chown opendkim:postfix /var/spool/postfix/opendkim
chmod 750 /var/spool/postfix/opendkim

# Firewall mail
if command -v ufw >/dev/null 2>&1; then
  ufw allow 25/tcp || true
  ufw allow 587/tcp || true
  ufw allow 465/tcp || true
  ufw allow 143/tcp || true
  ufw allow 993/tcp || true
  ufw allow 110/tcp || true
  ufw allow 995/tcp || true
fi

# Env panel
if [[ -f "$ENV_FILE" ]]; then
  grep -q '^VZONE_MAIL_STACK=' "$ENV_FILE" || echo "VZONE_MAIL_STACK=live" >> "$ENV_FILE"
  sed -i 's|^VZONE_MAIL_STACK=.*|VZONE_MAIL_STACK=live|' "$ENV_FILE"
  grep -q '^VZONE_MAIL_MAPS_DIR=' "$ENV_FILE" || echo "VZONE_MAIL_MAPS_DIR=${MAPS_DIR}" >> "$ENV_FILE"
  if [[ -n "${PUBLIC_IP}" ]]; then
    grep -q '^VZONE_MAIL_PUBLIC_IP=' "$ENV_FILE" || echo "VZONE_MAIL_PUBLIC_IP=${PUBLIC_IP}" >> "$ENV_FILE"
  fi
fi

systemctl enable --now opendkim
systemctl enable --now dovecot
systemctl enable --now postfix
systemctl reload opendkim || systemctl restart opendkim
systemctl reload dovecot || systemctl restart dovecot
systemctl reload postfix || systemctl restart postfix

echo "[vzone] Stack mail active — hostname=${HOSTNAME_FQDN} maps=${MAPS_DIR}"
echo "[vzone] Ports : 25/587/465 (SMTP) · 143/993 (IMAP) · 110/995 (POP3)"
echo "[vzone] Pensez à PTR rDNS + SPF/DKIM/DMARC pour la réputation."
