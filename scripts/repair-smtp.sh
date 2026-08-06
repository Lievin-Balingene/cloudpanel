#!/usr/bin/env bash
# Fix Roundcube 530 STARTTLS + 554 Access denied + 451 unavailable
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

echo "=== repair-smtp (0.32.10) — tls://127.0.0.1:587 ==="

mkdir -p "$MAPS_DIR"
for f in valiases virtual_mailboxes vdomains; do
  touch "${MAPS_DIR}/${f}"
  postmap "${MAPS_DIR}/${f}" 2>/dev/null || true
done

# Cert snakeoil
if [[ ! -f /etc/ssl/certs/ssl-cert-snakeoil.pem ]]; then
  apt-get install -y -qq ssl-cert 2>/dev/null || true
  make-ssl-cert generate-default-snakeoil --force-overwrite 2>/dev/null || true
fi

# Postfix
if [[ -f "${REPO_DIR}/deploy/postfix/main.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/main.cf" /etc/postfix/main.cf
  sed -i "s|__HOSTNAME__|${HOSTNAME_FQDN}|g" /etc/postfix/main.cf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/postfix/main.cf
fi
if [[ -f "${REPO_DIR}/deploy/postfix/master.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
fi

postconf -e "compatibility_level=2"
postconf -e "mynetworks=127.0.0.0/8 [::1]/128"
postconf -e "inet_interfaces=all"
postconf -e "inet_protocols=ipv4"
postconf -e "smtpd_tls_security_level=may"
postconf -e "smtpd_tls_auth_only=no"
postconf -e "smtpd_tls_cert_file=/etc/ssl/certs/ssl-cert-snakeoil.pem"
postconf -e "smtpd_tls_key_file=/etc/ssl/private/ssl-cert-snakeoil.key"
# Pas de milter tant que l'envoi ne marche pas (451 sinon)
postconf -e "smtpd_milters="
postconf -e "non_smtpd_milters="
postconf -e "milter_default_action=accept"

postfix check 2>&1 | tee /tmp/vzone-postfix-check.txt || true

systemctl enable postfix dovecot 2>/dev/null || true
systemctl stop postfix 2>/dev/null || true
pkill -x master 2>/dev/null || true
sleep 1
systemctl start postfix
systemctl restart dovecot 2>/dev/null || true

# Roundcube : ne PAS sed-détruire le fichier (cause « Oops »).
# On délègue à repair-roundcube.sh qui régénère proprement si besoin.
if [[ -f "${REPO_DIR}/scripts/repair-roundcube.sh" ]]; then
  FORCE_RC_REWRITE=0 bash "${REPO_DIR}/scripts/repair-roundcube.sh" || true
fi
# Forcer smtp tls via sed ligne unique seulement si syntaxe OK
RC_CFG="${RC_ROOT}/config/config.inc.php"
if [[ -f "$RC_CFG" ]] && php -l "$RC_CFG" >/dev/null 2>&1; then
  if grep -q "\$config\['smtp_host'\]" "$RC_CFG"; then
    sed -i "s|\$config\['smtp_host'\] = '.*'|\$config['smtp_host'] = 'tls://127.0.0.1:587'|" "$RC_CFG"
  fi
  if grep -q "\$config\['smtp_user'\]" "$RC_CFG"; then
    sed -i "s|\$config\['smtp_user'\] = '.*'|\$config['smtp_user'] = '%u'|" "$RC_CFG"
  fi
  if grep -q "\$config\['smtp_pass'\]" "$RC_CFG"; then
    sed -i "s|\$config\['smtp_pass'\] = '.*'|\$config['smtp_pass'] = '%p'|" "$RC_CFG"
  fi
  echo "[roundcube] smtp:"
  grep -n "smtp_host\|smtp_user\|smtp_pass" "$RC_CFG" | head -n 10
fi

systemctl restart php8.1-fpm 2>/dev/null || systemctl restart php8.2-fpm 2>/dev/null || systemctl restart php8.3-fpm 2>/dev/null || true

sleep 1
echo
echo "===== DIAG ====="
systemctl is-active postfix dovecot
ss -lntp | grep -E ':25 |:587 ' || true
echo "postconf submission TLS:"
postconf -h smtpd_tls_security_level smtpd_tls_cert_file mynetworks | cat

echo
echo "===== TEST STARTTLS :587 ====="
python3 - <<'PY'
import socket, ssl, sys
try:
    raw = socket.create_connection(("127.0.0.1", 587), 5)
    print(raw.recv(256).decode(errors="replace").strip())
    raw.sendall(b"EHLO localhost\r\n")
    print(raw.recv(1024).decode(errors="replace").split("\n")[0].strip())
    raw.sendall(b"STARTTLS\r\n")
    resp = raw.recv(256).decode(errors="replace").strip()
    print("STARTTLS:", resp)
    if not resp.startswith("220"):
        sys.exit(2)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    s = ctx.wrap_socket(raw, server_hostname="127.0.0.1")
    s.sendall(b"EHLO localhost\r\n")
    print(s.recv(1024).decode(errors="replace").split("\n")[0].strip())
    print("TLS_OK")
    s.sendall(b"QUIT\r\n")
    s.close()
except Exception as e:
    print("TLS_FAIL:", e)
    sys.exit(1)
PY

echo
echo "=== Suite ==="
echo "1) Déconnexion Roundcube + Ctrl+F5"
echo "2) Reconnexion avec info@7une.info + mot de passe"
echo "3) Renvoyer un mail"
echo "Si 535 auth: doveadm auth test info@7une.info 'MOTDEPASSE'"
echo "=== OK ==="
