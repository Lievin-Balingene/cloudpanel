#!/usr/bin/env bash
# Active DKIM SANS casser le SMTP : test + rollback auto si échec.
# Prérequis: envoi Roundcube déjà OK (repair-smtp.sh).
# Usage: sudo bash /opt/vzone-src/scripts/repair-dkim.sh
set -uo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
[[ -f "$ENV_FILE" ]] && { set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a; }

MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-/var/lib/vzone/mail/maps}"
HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"
SOCK="/var/spool/postfix/opendkim/opendkim.sock"
MASTER_BAK="/etc/postfix/master.cf.vzone-pre-dkim"

rollback_smtp() {
  echo "[rollback] Coupe milters — SMTP intact"
  postconf -e "smtpd_milters="
  postconf -e "non_smtpd_milters="
  if [[ -f "$MASTER_BAK" ]]; then
    cp -a "$MASTER_BAK" /etc/postfix/master.cf
  elif [[ -f "${REPO_DIR}/deploy/postfix/master.cf" ]]; then
    install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
  fi
  # Forcer milters vides dans master.cf submission
  sed -i 's/-o smtpd_milters=.*/-o smtpd_milters=/' /etc/postfix/master.cf 2>/dev/null || true
  systemctl reload postfix 2>/dev/null || systemctl restart postfix
  echo "Relancez Roundcube — l'envoi doit marcher. DKIM non activé."
}

echo "=== repair-dkim (0.32.17) — test + rollback ==="

# 0) Sauvegarde master sans DKIM
cp -a /etc/postfix/master.cf "$MASTER_BAK"

# 1) Préparer OpenDKIM (sans toucher Postfix encore)
mkdir -p "${MAPS_DIR}/dkim" /var/spool/postfix/opendkim
chown opendkim:postfix /var/spool/postfix/opendkim
chmod 750 /var/spool/postfix/opendkim

install -m 644 "${REPO_DIR}/deploy/opendkim/opendkim.conf" /etc/opendkim.conf
sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/opendkim.conf
sed -i 's/^Mode.*/Mode                    s/' /etc/opendkim.conf

install -m 644 "${REPO_DIR}/deploy/opendkim/TrustedHosts" /etc/opendkim/TrustedHosts
for h in 127.0.0.1 localhost ::1 "$HOSTNAME_FQDN"; do
  grep -qxF "$h" /etc/opendkim/TrustedHosts || echo "$h" >> /etc/opendkim/TrustedHosts
done

export DJANGO_SETTINGS_MODULE=vzone.settings.production
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY'
from apps.email.models import MailDomain
from apps.email.services import ensure_mail_reputation, write_mail_maps
for md in MailDomain.objects.filter(is_active=True):
    try:
        print(md.name, ensure_mail_reputation(md).get("dkim"))
    except Exception as e:
        print(md.name, "ERR", e)
write_mail_maps()
PY
fi

chgrp -R opendkim "${MAPS_DIR}/dkim" 2>/dev/null || true
chmod -R g+rX "${MAPS_DIR}/dkim" 2>/dev/null || true
find "${MAPS_DIR}/dkim" -name '*.private' -exec chmod 640 {} \; 2>/dev/null || true
# opendkim doit lire les maps
chgrp opendkim "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true
chmod 640 "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true
# Accès au répertoire maps
chmod 750 "$MAPS_DIR" 2>/dev/null || true
usermod -aG "$(stat -c %G "$MAPS_DIR" 2>/dev/null || echo opendkim)" opendkim 2>/dev/null || true

if [[ ! -s "${MAPS_DIR}/opendkim-SigningTable" ]] || [[ ! -s "${MAPS_DIR}/opendkim-KeyTable" ]]; then
  echo "ERREUR: tables DKIM vides — activez DKIM dans Email panel d'abord"
  exit 1
fi

echo "--- SigningTable ---"
cat "${MAPS_DIR}/opendkim-SigningTable"
echo "--- KeyTable ---"
cat "${MAPS_DIR}/opendkim-KeyTable"

# Vérifier que chaque clé privée existe et est lisible par opendkim
while read -r _line; do
  [[ -z "$_line" || "$_line" =~ ^# ]] && continue
  keypath="$(echo "$_line" | awk -F: '{print $NF}')"
  if [[ ! -f "$keypath" ]]; then
    echo "ERREUR: clé absente: $keypath"
    exit 1
  fi
  if ! sudo -u opendkim test -r "$keypath" 2>/dev/null; then
    echo "ERREUR: opendkim ne peut pas lire $keypath"
    ls -la "$keypath"
    exit 1
  fi
done < "${MAPS_DIR}/opendkim-KeyTable"

systemctl enable --now opendkim
rm -f "$SOCK"
systemctl restart opendkim
sleep 2

if [[ ! -S "$SOCK" ]]; then
  echo "ERREUR: socket $SOCK absent"
  journalctl -u opendkim -n 40 --no-pager || true
  exit 1
fi
chmod 660 "$SOCK" 2>/dev/null || true
chown opendkim:postfix "$SOCK" 2>/dev/null || true

# 2) Valider clé PEM + test signature (CRLF obligatoire pour opendkim-testmsg)
DOMAIN="$(awk 'NF{print $1; exit}' "${MAPS_DIR}/opendkim-SigningTable" | sed 's/.*@//')"
KEYFILE="${MAPS_DIR}/dkim/${DOMAIN}/default.private"
if [[ ! -f "$KEYFILE" ]]; then
  echo "ERREUR: clé privée absente: $KEYFILE"
  exit 1
fi
# Première ligne PEM (BOM / ligne vide = OpenDKIM lit en DER et échoue)
head -1 "$KEYFILE" | grep -qE '^-----BEGIN (RSA )?PRIVATE KEY-----$' || {
  echo "ERREUR: clé PEM invalide (attendu BEGIN RSA/PRIVATE KEY):"
  head -3 "$KEYFILE" | cat -A
  exit 1
}
if command -v openssl >/dev/null 2>&1; then
  if ! openssl rsa -in "$KEYFILE" -check -noout 2>/tmp/dkim-openssl.txt; then
    echo "ERREUR: openssl refuse la clé privée:"
    cat /tmp/dkim-openssl.txt || true
    exit 1
  fi
  echo "openssl clé OK"
fi
# opendkim-testmsg exige des CRLF (\r\n) — LF seul → dkim_chunk(): Syntax error
if command -v opendkim-testmsg >/dev/null 2>&1; then
  printf 'From: test@%s\r\nTo: a@b.com\r\nSubject: t\r\n\r\nhi\r\n' "$DOMAIN" \
    | opendkim-testmsg -d "$DOMAIN" -s default -k "$KEYFILE" >/tmp/dkim-out.eml 2>/tmp/dkim-err.txt
  if [[ $? -ne 0 ]] || ! grep -q '^DKIM-Signature:' /tmp/dkim-out.eml 2>/dev/null; then
    echo "AVERTISSEMENT: opendkim-testmsg a échoué (clé openssl OK — on continue):"
    cat /tmp/dkim-err.txt 2>/dev/null || true
  else
    echo "opendkim-testmsg OK"
  fi
fi

# 3) Activer milter UNIQUEMENT sur submission + ORIGINATING (unix socket)
MILTER="local:${SOCK}"
postconf -e "milter_default_action=accept"
postconf -e "milter_protocol=6"
postconf -e "milter_connect_timeout=5s"
postconf -e "milter_command_timeout=10s"
postconf -e "smtpd_milters="
postconf -e "non_smtpd_milters="

# Postfix doit pouvoir ouvrir le socket OpenDKIM
usermod -aG opendkim postfix 2>/dev/null || true
# IP publique = host interne (signature)
PUB_IP="$(postconf -h inet_interfaces 2>/dev/null | tr ' ,' '\n' | grep -E '^[0-9.]+$' | head -1 || true)"
[[ -z "$PUB_IP" || "$PUB_IP" == "all" ]] && PUB_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
for h in 127.0.0.1 localhost ::1 "$HOSTNAME_FQDN" ${PUB_IP:-}; do
  [[ -n "$h" ]] || continue
  grep -qxF "$h" /etc/opendkim/TrustedHosts || echo "$h" >> /etc/opendkim/TrustedHosts
done
systemctl restart opendkim
sleep 1
chmod 660 "$SOCK" 2>/dev/null || true
chown opendkim:postfix "$SOCK" 2>/dev/null || true

install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
# IMPORTANT: lignes master.cf indentées — matcher "  -o smtpd_milters=" (pas ^-o)
awk -v milter="$MILTER" '
  BEGIN { subm=0 }
  /^[a-zA-Z]/ {
    if ($1 == "submission" || $1 == "smtps") subm=1
    else subm=0
  }
  /^[ \t]*-o[ \t]+smtpd_milters=/ && subm {
    print "  -o smtpd_milters=" milter
    print "  -o milter_macro_daemon_name=ORIGINATING"
    next
  }
  { print }
' /etc/postfix/master.cf > /tmp/master.cf.dkim
mv /tmp/master.cf.dkim /etc/postfix/master.cf

if ! grep -E '^[ \t]*-o[ \t]+smtpd_milters=.*opendkim' /etc/postfix/master.cf >/dev/null; then
  echo "ERREUR: milter OpenDKIM non injecté dans master.cf"
  grep -n 'smtpd_milters' /etc/postfix/master.cf || true
  exit 1
fi
if ! grep -q 'milter_macro_daemon_name=ORIGINATING' /etc/postfix/master.cf; then
  echo "ERREUR: ORIGINATING manquant dans master.cf"
  exit 1
fi
echo "--- master.cf submission (milters) ---"
awk '/^submission /{p=1} /^[a-zA-Z]/ && !/^submission /{p=0} p' /etc/postfix/master.cf | grep -E 'milter|ORIGINATING' || true

systemctl reload postfix 2>/dev/null || systemctl restart postfix
sleep 1

# 4) Test SMTP :587 STARTTLS (sans auth) — milter ne doit pas faire planter le dialogue EHLO/STARTTLS
if ! python3 - <<'PY'
import socket, ssl, sys
try:
    raw = socket.create_connection(("127.0.0.1", 587), 5)
    raw.recv(256)
    raw.sendall(b"EHLO localhost\r\n"); raw.recv(1024)
    raw.sendall(b"STARTTLS\r\n")
    r = raw.recv(256).decode(errors="replace")
    if not r.startswith("220"):
        print("STARTTLS fail", r); sys.exit(1)
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    s = ctx.wrap_socket(raw, server_hostname="127.0.0.1")
    s.sendall(b"EHLO localhost\r\n"); s.recv(1024)
    s.sendall(b"QUIT\r\n"); s.close()
    print("SMTP_DIALOG_OK")
except Exception as e:
    print("SMTP_DIALOG_FAIL", e); sys.exit(1)
PY
then
  echo "ECHEC: dialogue SMTP cassé après activation milter"
  rollback_smtp
  exit 1
fi

echo
echo "DKIM milter activé sur submission ($MILTER) + ORIGINATING"
echo "Testez Roundcube MAINTENANT."
echo "Si « SMTP unavailable » → sudo bash ${REPO_DIR}/scripts/repair-smtp.sh"
echo "=== repair-dkim OK ==="
