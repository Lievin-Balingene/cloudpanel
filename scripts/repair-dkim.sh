#!/usr/bin/env bash
# Active / répare DKIM (OpenDKIM) sans casser le SMTP Roundcube.
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

echo "=== repair-dkim (0.32.12) ==="

mkdir -p "${MAPS_DIR}/dkim"
touch "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable"

# Conf OpenDKIM → tables panel
if [[ -f "${REPO_DIR}/deploy/opendkim/opendkim.conf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/opendkim/opendkim.conf" /etc/opendkim.conf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/opendkim.conf
fi
if [[ -f "${REPO_DIR}/deploy/opendkim/TrustedHosts" ]]; then
  install -m 644 "${REPO_DIR}/deploy/opendkim/TrustedHosts" /etc/opendkim/TrustedHosts
fi
for h in 127.0.0.1 localhost ::1 "$HOSTNAME_FQDN"; do
  grep -qxF "$h" /etc/opendkim/TrustedHosts 2>/dev/null || echo "$h" >> /etc/opendkim/TrustedHosts
done

# Régénérer clés + DNS + maps via Django
export DJANGO_SETTINGS_MODULE=vzone.settings.production
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  echo "[django] ensure_mail_reputation…"
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY'
from apps.email.models import MailDomain
from apps.email.services import ensure_mail_reputation, write_mail_maps

for md in MailDomain.objects.filter(is_active=True):
    try:
        info = ensure_mail_reputation(md)
        print(f"  ✓ {md.name}: dkim={info.get('dkim')} selector={getattr(md,'dkim_selector',None)}")
    except Exception as exc:
        print(f"  ! {md.name}: {exc}")
write_mail_maps()
print("maps OK")
PY
else
  echo "[warn] venv Django introuvable — maps manuelles seulement"
fi

# Permissions
chgrp -R opendkim "${MAPS_DIR}/dkim" 2>/dev/null || true
chmod -R g+rX "${MAPS_DIR}/dkim" 2>/dev/null || true
find "${MAPS_DIR}/dkim" -type f -name '*.private' -exec chmod 640 {} \; 2>/dev/null || true
chgrp opendkim "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true
chmod 640 "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true
# Miroir /etc
cp -f "${MAPS_DIR}/opendkim-KeyTable" /etc/opendkim/KeyTable 2>/dev/null || true
cp -f "${MAPS_DIR}/opendkim-SigningTable" /etc/opendkim/SigningTable 2>/dev/null || true
chown opendkim:opendkim /etc/opendkim/KeyTable /etc/opendkim/SigningTable 2>/dev/null || true

# Agent mail reload
if [[ -f "${REPO_DIR}/scripts/vzone-mail-reload.sh" ]]; then
  install -m 755 "${REPO_DIR}/scripts/vzone-mail-reload.sh" /usr/local/sbin/vzone-mail-reload
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-mail-reload.service" /etc/systemd/system/vzone-mail-reload.service
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-mail-reload.path" /etc/systemd/system/vzone-mail-reload.path
  systemctl daemon-reload
  systemctl enable --now vzone-mail-reload.path 2>/dev/null || true
fi

# Postfix milters ON (accept si down)
if [[ -f "${REPO_DIR}/deploy/postfix/main.cf" ]]; then
  # Ne pas écraser tout main.cf ici — postconf suffit
  true
fi
postconf -e "milter_default_action=accept"
postconf -e "milter_protocol=6"
postconf -e "smtpd_milters=inet:127.0.0.1:8891"
postconf -e "non_smtpd_milters=inet:127.0.0.1:8891"

# master.cf : s'assurer milter sur submission
if [[ -f "${REPO_DIR}/deploy/postfix/master.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
fi

systemctl enable --now opendkim 2>/dev/null || true
systemctl restart opendkim
sleep 1
systemctl reload postfix 2>/dev/null || systemctl restart postfix

echo
echo "===== DIAG DKIM ====="
systemctl is-active opendkim postfix
ss -lntp | grep 8891 || echo "WARN: OpenDKIM n'écoute pas sur :8891"
echo "--- SigningTable ---"
cat "${MAPS_DIR}/opendkim-SigningTable" || true
echo "--- KeyTable ---"
cat "${MAPS_DIR}/opendkim-KeyTable" || true
echo "--- postconf milters ---"
postconf -h smtpd_milters milter_default_action

echo
echo "--- DNS DKIM (local BIND) ---"
for d in $(awk '{print $1}' "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null | sed 's/.*@//' | sort -u); do
  echo "dig TXT default._domainkey.$d"
  dig +short TXT "default._domainkey.$d" @127.0.0.1 2>/dev/null | head -n 2 || true
  dig +short TXT "default._domainkey.$d" 2>/dev/null | head -n 2 || true
done

echo
echo "=== Test ==="
echo "1) Envoyez un mail depuis Roundcube"
echo "2) https://www.mail-tester.com → DKIM doit être pass"
echo "3) grep DKIM /var/log/mail.log | tail"
echo "=== repair-dkim OK ==="
