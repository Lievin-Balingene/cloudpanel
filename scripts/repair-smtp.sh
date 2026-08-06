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

echo "=== repair-smtp (0.32.8) ==="
echo "hostname=$HOSTNAME_FQDN maps=$MAPS_DIR"

mkdir -p "$MAPS_DIR/dkim"
for f in opendkim-KeyTable opendkim-SigningTable valiases virtual_mailboxes vdomains; do
  touch "${MAPS_DIR}/${f}"
done
# hash maps vides → fichiers .db
postmap "${MAPS_DIR}/valiases" 2>/dev/null || true
postmap "${MAPS_DIR}/virtual_mailboxes" 2>/dev/null || true
postmap "${MAPS_DIR}/vdomains" 2>/dev/null || true

# Certificats TLS (sinon submission plante)
if [[ ! -f /etc/ssl/certs/ssl-cert-snakeoil.pem ]]; then
  apt-get install -y -qq ssl-cert 2>/dev/null || true
  make-ssl-cert generate-default-snakeoil --force-overwrite 2>/dev/null || true
fi

# --- main.cf ---
if [[ -f "${REPO_DIR}/deploy/postfix/main.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/main.cf" /etc/postfix/main.cf
  sed -i "s|__HOSTNAME__|${HOSTNAME_FQDN}|g" /etc/postfix/main.cf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/postfix/main.cf
fi
# Forcer un compatibility_level supporté (3.6 casse Postfix 3.4 / Ubuntu 20.04)
postconf -e "compatibility_level=2" 2>/dev/null || true
postconf -e "mynetworks=127.0.0.0/8 [::1]/128" 2>/dev/null || true
postconf -e "inet_interfaces=all" 2>/dev/null || true
postconf -e "smtpd_tls_security_level=may" 2>/dev/null || true
# Milters OFF d'abord (réactiver si OpenDKIM OK)
postconf -e "smtpd_milters=" 2>/dev/null || true
postconf -e "non_smtpd_milters=" 2>/dev/null || true
postconf -e "milter_default_action=accept" 2>/dev/null || true

# --- master.cf ---
if [[ -f "${REPO_DIR}/deploy/postfix/master.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
fi
sed -i '/^postlog[[:space:]]/d' /etc/postfix/master.cf 2>/dev/null || true
# Sur submission aussi : pas de milter tant que SMTP local ne marche pas
sed -i '/smtpd_milters=/d' /etc/postfix/master.cf 2>/dev/null || true

# Si master.cf cassé → restaurer le dist Ubuntu puis réinjecter submission
if ! postfix check >/tmp/vzone-postfix-check.txt 2>&1; then
  echo "[warn] postfix check KO — restauration master.cf.dist"
  cat /tmp/vzone-postfix-check.txt || true
  if [[ -f /usr/share/postfix/master.cf.dist ]]; then
    cp -a /usr/share/postfix/master.cf.dist /etc/postfix/master.cf
    # Décommenter / assurer submission
    if grep -qE '^#submission' /etc/postfix/master.cf; then
      sed -i 's/^#submission/submission/' /etc/postfix/master.cf
    fi
  fi
fi

# OpenDKIM conf (ne bloque pas le SMTP)
if [[ -f "${REPO_DIR}/deploy/opendkim/opendkim.conf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/opendkim/opendkim.conf" /etc/opendkim.conf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/opendkim.conf
fi
if [[ -f "${REPO_DIR}/deploy/opendkim/TrustedHosts" ]]; then
  install -m 644 "${REPO_DIR}/deploy/opendkim/TrustedHosts" /etc/opendkim/TrustedHosts
  for h in 127.0.0.1 localhost ::1 "$HOSTNAME_FQDN"; do
    grep -qxF "$h" /etc/opendkim/TrustedHosts || echo "$h" >> /etc/opendkim/TrustedHosts
  done
fi
chgrp opendkim "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true
chmod 640 "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true

# --- Roundcube : SMTP plain :25, sans auth ---
RC_CFG="${RC_ROOT}/config/config.inc.php"
if [[ -f "$RC_CFG" ]]; then
  echo "[roundcube] force smtp 127.0.0.1:25"
  # Supprimer anciennes lignes smtp_* puis réécrire un bloc clair
  sed -i "/\$config\['smtp_host'\]/d" "$RC_CFG"
  sed -i "/\$config\['smtp_user'\]/d" "$RC_CFG"
  sed -i "/\$config\['smtp_pass'\]/d" "$RC_CFG"
  sed -i "/\$config\['smtp_port'\]/d" "$RC_CFG"
  sed -i "/\$config\['smtp_server'\]/d" "$RC_CFG"
  sed -i "/\$config\['smtp_helo_host'\]/d" "$RC_CFG"
  cat >> "$RC_CFG" <<'PHP'

// V-zone repair-smtp — SMTP local (mynetworks)
$config['smtp_host'] = '127.0.0.1:25';
$config['smtp_user'] = '';
$config['smtp_pass'] = '';
$config['smtp_helo_host'] = 'localhost';
PHP
  # Afficher résultat
  grep -E "smtp_host|smtp_user|smtp_pass" "$RC_CFG" | tail -n 6 || true
else
  echo "[warn] Roundcube config absente: $RC_CFG"
fi

systemctl reload php*-fpm 2>/dev/null || systemctl restart php8.1-fpm 2>/dev/null || systemctl restart php8.3-fpm 2>/dev/null || true

echo "[postfix] restart…"
systemctl enable postfix 2>/dev/null || true
systemctl stop postfix 2>/dev/null || true
# Tuer un master zombie
pkill -x master 2>/dev/null || true
sleep 1
if ! systemctl start postfix 2>&1; then
  echo "ERREUR start postfix"
  journalctl -u postfix -n 50 --no-pager || true
  postfix start 2>&1 || true
fi
systemctl enable --now dovecot 2>/dev/null || true
systemctl restart opendkim 2>/dev/null || true

sleep 2
echo
echo "===== DIAGNOSTIC ====="
echo -n "postfix: "; systemctl is-active postfix || true
echo -n "dovecot: "; systemctl is-active dovecot || true
echo -n "opendkim: "; systemctl is-active opendkim || true
echo "compatibility_level=$(postconf -h compatibility_level 2>/dev/null || echo '?')"
echo "smtpd_milters=$(postconf -h smtpd_milters 2>/dev/null || echo '?')"
echo "mynetworks=$(postconf -h mynetworks 2>/dev/null || echo '?')"
echo "ports:"
ss -lntp 2>/dev/null | grep -E ':25 |:587 |:465 ' || echo "(aucun port SMTP en écoute !)"

echo
echo "===== TEST SMTP LOCAL :25 ====="
python3 - <<'PY' || true
import socket, sys
try:
    s = socket.create_connection(("127.0.0.1", 25), timeout=5)
    banner = s.recv(256).decode("utf-8", "replace")
    print("banner:", banner.strip())
    s.sendall(b"EHLO localhost\r\n")
    print(s.recv(1024).decode("utf-8", "replace").strip().split("\n")[0])
    s.sendall(b"MAIL FROM:<test@localhost>\r\n")
    print("MAIL:", s.recv(256).decode("utf-8", "replace").strip())
    s.sendall(b"RCPT TO:<test@localhost>\r\n")
    print("RCPT:", s.recv(256).decode("utf-8", "replace").strip())
    s.sendall(b"QUIT\r\n")
    s.close()
    print("SMTP_OK")
except Exception as e:
    print("SMTP_FAIL:", e)
    sys.exit(1)
PY

# Réactiver OpenDKIM milter seulement si le socket répond
if ss -lntp 2>/dev/null | grep -q ':8891'; then
  echo "[opendkim] port 8891 OK → réactivation milters"
  postconf -e "smtpd_milters=inet:127.0.0.1:8891"
  postconf -e "non_smtpd_milters=inet:127.0.0.1:8891"
  postconf -e "milter_default_action=accept"
  systemctl reload postfix 2>/dev/null || systemctl restart postfix 2>/dev/null || true
else
  echo "[opendkim] 8891 absent → milters restent désactivés (mail OK sans DKIM)"
fi

echo
echo "=== Suite ==="
echo "1) Rechargez Roundcube (Ctrl+F5) et renvoyez un mail"
echo "2) Si échec: journalctl -u postfix -n 60 --no-pager"
echo "3) Et: tail -n 40 ${RC_ROOT}/logs/errors.log"
echo "=== repair-smtp OK ==="
