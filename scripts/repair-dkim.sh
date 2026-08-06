#!/usr/bin/env bash
# Active DKIM sans jamais laisser SMTP cassé.
# - OpenDKIM On-InternalError=accept (pas de 451)
# - milter inet:8891
# - test AUTH+DATA obligatoire ; rollback auto si 4xx
# Prérequis: repair-smtp.sh déjà OK.
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
MILTER="inet:127.0.0.1:8891"
MASTER_BAK="/etc/postfix/master.cf.vzone-pre-dkim"
PY="${VZONE_ROOT}/backend/.venv/bin/python"
[[ -x "$PY" ]] || PY="python3"

rollback_smtp() {
  echo "[rollback] Coupe milters — SMTP prioritaire"
  bash "${REPO_DIR}/scripts/repair-smtp.sh" >/tmp/repair-smtp-rollback.log 2>&1 || {
    postconf -e "smtpd_milters=" "non_smtpd_milters=" "milter_default_action=accept"
    install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
    systemctl reload postfix 2>/dev/null || systemctl restart postfix
  }
  echo "SMTP rétabli. DKIM NON actif. Voir /tmp/repair-smtp-rollback.log"
}

echo "=== repair-dkim (0.32.18) — safe + AUTH test + rollback ==="

# 0) Toujours partir d'un master SANS milter (sauvegarde propre)
install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
cp -a /etc/postfix/master.cf "$MASTER_BAK"
postconf -e "smtpd_milters=" "non_smtpd_milters=" "milter_default_action=accept"

# 1) OpenDKIM (tables sous /etc/opendkim — lisibles)
mkdir -p /etc/opendkim/keys "${MAPS_DIR}/dkim"
install -m 644 "${REPO_DIR}/deploy/opendkim/opendkim.conf" /etc/opendkim.conf
install -m 644 "${REPO_DIR}/deploy/opendkim/TrustedHosts" /etc/opendkim/TrustedHosts
PUB_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
for h in 127.0.0.1 localhost ::1 "$HOSTNAME_FQDN" ${PUB_IP:-}; do
  [[ -n "$h" ]] || continue
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

# Sync maps panel → /etc/opendkim + clés sous /etc/opendkim/keys/<domaine>/
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
    install -m 640 -o opendkim -g opendkim "$src" "${dest_dir}/${selector}.private"
    echo "${key_id} ${domain}:${selector}:${dest_dir}/${selector}.private" >> /etc/opendkim/KeyTable
  done < "${MAPS_DIR}/opendkim-KeyTable"
fi
if [[ -s "${MAPS_DIR}/opendkim-SigningTable" ]]; then
  cp -f "${MAPS_DIR}/opendkim-SigningTable" /etc/opendkim/SigningTable
fi
chown -R opendkim:opendkim /etc/opendkim
chmod 644 /etc/opendkim/KeyTable /etc/opendkim/SigningTable /etc/opendkim/TrustedHosts
chmod 640 /etc/opendkim/keys/*/*.private 2>/dev/null || true
chown opendkim:opendkim /etc/opendkim.conf

if [[ ! -s /etc/opendkim/KeyTable ]] || [[ ! -s /etc/opendkim/SigningTable ]]; then
  echo "ERREUR: tables DKIM vides — activez DKIM dans le panel Email d'abord"
  exit 1
fi

echo "--- SigningTable ---"; cat /etc/opendkim/SigningTable
echo "--- KeyTable ---"; cat /etc/opendkim/KeyTable

# openssl check
while read -r line; do
  [[ -z "$line" || "$line" =~ ^# ]] && continue
  kp="$(echo "$line" | awk -F: '{print $NF}')"
  openssl rsa -in "$kp" -check -noout >/dev/null 2>&1 || {
    echo "ERREUR: clé invalide $kp"; exit 1;
  }
done < /etc/opendkim/KeyTable
echo "openssl clés OK"

systemctl enable --now opendkim
systemctl restart opendkim
sleep 2
if ! ss -ltn 2>/dev/null | grep -q ':8891 '; then
  echo "ERREUR: OpenDKIM n'écoute pas sur 127.0.0.1:8891"
  journalctl -u opendkim -n 40 --no-pager || true
  exit 1
fi
echo "opendkim :8891 OK"

# 2) Injecter milter submission/smtps + ORIGINATING
awk -v milter="$MILTER" '
  BEGIN { subm=0 }
  /^[a-zA-Z]/ {
    if ($1 == "submission" || $1 == "smtps") subm=1
    else subm=0
  }
  /^[ \t]*-o[ \t]+smtpd_milters=/ && subm {
    print "  -o smtpd_milters=" milter
    print "  -o milter_macro_daemon_name=ORIGINATING"
    print "  -o milter_default_action=accept"
    next
  }
  { print }
' /etc/postfix/master.cf > /tmp/master.cf.dkim
mv /tmp/master.cf.dkim /etc/postfix/master.cf

if ! grep -qE 'smtpd_milters=inet:127.0.0.1:8891' /etc/postfix/master.cf; then
  echo "ERREUR: milter non injecté"; rollback_smtp; exit 1
fi

postconf -e "milter_default_action=accept" "milter_protocol=6" \
  "milter_connect_timeout=5s" "milter_command_timeout=15s" \
  "smtpd_milters=" "non_smtpd_milters="

systemctl reload postfix 2>/dev/null || systemctl restart postfix
sleep 1

# 3) Test AUTH + DATA (là où Roundcube casse) — rollback si 4xx
export VZONE_ROOT MAPS_DIR
set +e
"$PY" <<'PY'
import os, ssl, sys
from pathlib import Path

root = os.environ.get("VZONE_ROOT", "/opt/vzone")
sys.path.insert(0, str(Path(root) / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vzone.settings.production")
try:
    import django
    django.setup()
    from apps.email.models import Mailbox
    box = (
        Mailbox.objects.filter(is_active=True, is_suspended=False)
        .select_related("mail_domain")
        .first()
    )
    if not box:
        print("NO_MAILBOX")
        sys.exit(2)
    user = box.address
    password = box.get_password_plain() if hasattr(box, "get_password_plain") else None
    if not password:
        print("NO_PASSWORD", user)
        sys.exit(2)
except Exception as e:
    print("DJANGO_FAIL", e)
    sys.exit(2)

import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg["From"] = user
msg["To"] = user
msg["Subject"] = "vzone-dkim-probe"
msg.set_content("dkim probe — safe to ignore")

try:
    with smtplib.SMTP("127.0.0.1", 587, timeout=20) as s:
        s.ehlo()
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        s.starttls(context=context)
        s.ehlo()
        s.login(user, password)
        s.send_message(msg)
    print("AUTH_DATA_OK", user)
except smtplib.SMTPDataError as e:
    print("SMTP_DATA_FAIL", e.smtp_code, e.smtp_error)
    sys.exit(1)
except smtplib.SMTPResponseException as e:
    print("SMTP_FAIL", getattr(e, "smtp_code", "?"), e)
    sys.exit(1)
except Exception as e:
    print("SMTP_FAIL", e)
    sys.exit(1)
PY
auth_rc=$?
set -u
# pipefail already on; do not re-enable -e (script uses set -uo pipefail)

if [[ "$auth_rc" -eq 1 ]]; then
  echo "ECHEC: AUTH/DATA SMTP après milter — rollback"
  journalctl -u opendkim -u postfix --since "2 min ago" --no-pager 2>/dev/null | tail -40 || true
  rollback_smtp
  exit 1
elif [[ "$auth_rc" -eq 2 ]]; then
  echo "AVERTISSEMENT: pas de boîte/mot de passe pour test AUTH"
  echo "Milter actif avec On-InternalError=accept. Si Roundcube fail → repair-smtp (timer auto)."
else
  echo "AUTH_DATA_OK — milter n'a pas cassé l'envoi"
fi

# 4) Timer garde SMTP
if [[ -f "${REPO_DIR}/deploy/systemd/vzone-smtp-guard.timer" ]]; then
  sed "s|/opt/vzone-src|${REPO_DIR}|g" \
    "${REPO_DIR}/deploy/systemd/vzone-smtp-guard.service" > /etc/systemd/system/vzone-smtp-guard.service
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-smtp-guard.timer" /etc/systemd/system/vzone-smtp-guard.timer
  chmod 755 "${REPO_DIR}/scripts/vzone-smtp-guard.sh"
  systemctl daemon-reload
  systemctl enable --now vzone-smtp-guard.timer 2>/dev/null || true
fi

echo
echo "DKIM milter: $MILTER (On-InternalError=accept)"
echo "Si Roundcube fail encore → sudo bash ${REPO_DIR}/scripts/repair-smtp.sh"
echo "Le timer vzone-smtp-guard coupe auto les milters si 451 revient."
echo "=== repair-dkim OK ==="
