#!/usr/bin/env bash
# Active DKIM correctement : milter + ORIGINATING sur submission uniquement.
# Prérequis : SMTP déjà OK via repair-smtp.sh
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

echo "=== repair-dkim (0.32.14) — ORIGINATING ==="

mkdir -p "${MAPS_DIR}/dkim"
touch "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable"

install -m 644 "${REPO_DIR}/deploy/opendkim/opendkim.conf" /etc/opendkim.conf
sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/opendkim.conf
# Forcer Mode sign-only
sed -i 's/^Mode.*/Mode                    s/' /etc/opendkim.conf
grep -q '^Mode' /etc/opendkim.conf || echo 'Mode                    s' >> /etc/opendkim.conf

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
        print(md.name, e)
write_mail_maps()
PY
fi

chgrp -R opendkim "${MAPS_DIR}/dkim" 2>/dev/null || true
chmod -R g+rX "${MAPS_DIR}/dkim" 2>/dev/null || true
find "${MAPS_DIR}/dkim" -name '*.private' -exec chmod 640 {} \; 2>/dev/null || true
chgrp opendkim "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable"
chmod 640 "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable"
cp -f "${MAPS_DIR}/opendkim-KeyTable" /etc/opendkim/KeyTable
cp -f "${MAPS_DIR}/opendkim-SigningTable" /etc/opendkim/SigningTable
chown opendkim:opendkim /etc/opendkim/KeyTable /etc/opendkim/SigningTable

if [[ ! -s "${MAPS_DIR}/opendkim-SigningTable" ]]; then
  echo "ERREUR: SigningTable vide — activez DKIM dans le panel Email d'abord"
  exit 1
fi

systemctl enable --now opendkim
systemctl restart opendkim
sleep 2
if ! ss -lntp 2>/dev/null | grep -q ':8891'; then
  echo "ERREUR: OpenDKIM :8891 down — abort (SMTP inchangé)"
  journalctl -u opendkim -n 40 --no-pager || true
  exit 1
fi

# master.cf AVEC milter + ORIGINATING sur submission
install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
# main.cf : pas de milter global
postconf -e "smtpd_milters="
postconf -e "non_smtpd_milters="
postconf -e "milter_default_action=accept"

systemctl reload postfix 2>/dev/null || systemctl restart postfix

echo
echo "--- SigningTable ---"
cat "${MAPS_DIR}/opendkim-SigningTable"
echo "opendkim=$(systemctl is-active opendkim) :8891 OK"
echo "submission milter: ORIGINATING + 127.0.0.1:8891"
echo
echo "Test: envoyez un mail. Si 451 → sudo bash ${REPO_DIR}/scripts/repair-smtp.sh"
echo "=== repair-dkim OK ==="
