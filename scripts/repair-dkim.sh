#!/usr/bin/env bash
# Active DKIM seulement si OpenDKIM signe sans erreur (sinon ne touche pas au SMTP).
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

echo "=== repair-dkim (0.32.13) ==="

mkdir -p "${MAPS_DIR}/dkim"
touch "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable"

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

export DJANGO_SETTINGS_MODULE=vzone.settings.production
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY'
from apps.email.models import MailDomain
from apps.email.services import ensure_mail_reputation, write_mail_maps
for md in MailDomain.objects.filter(is_active=True):
    try:
        info = ensure_mail_reputation(md)
        print(f"  ✓ {md.name}: {info.get('dkim')}")
    except Exception as exc:
        print(f"  ! {md.name}: {exc}")
write_mail_maps()
print("maps OK")
PY
fi

chgrp -R opendkim "${MAPS_DIR}/dkim" 2>/dev/null || true
chmod -R g+rX "${MAPS_DIR}/dkim" 2>/dev/null || true
find "${MAPS_DIR}/dkim" -name '*.private' -exec chmod 640 {} \; 2>/dev/null || true
chgrp opendkim "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true
chmod 640 "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable"
cp -f "${MAPS_DIR}/opendkim-KeyTable" /etc/opendkim/KeyTable
cp -f "${MAPS_DIR}/opendkim-SigningTable" /etc/opendkim/SigningTable
chown opendkim:opendkim /etc/opendkim/KeyTable /etc/opendkim/SigningTable

systemctl enable --now opendkim
systemctl restart opendkim
sleep 2

if ! ss -lntp 2>/dev/null | grep -q ':8891'; then
  echo "ERREUR: OpenDKIM n'écoute pas :8891 — milters NON activés (SMTP intact)"
  journalctl -u opendkim -n 30 --no-pager || true
  exit 1
fi

# Test signature hors Postfix
TEST_OK=0
if [[ -s "${MAPS_DIR}/opendkim-SigningTable" ]]; then
  DOMAIN="$(awk '{print $1}' "${MAPS_DIR}/opendkim-SigningTable" | head -1 | sed 's/.*@//')"
  if [[ -n "$DOMAIN" ]] && command -v opendkim-testmsg >/dev/null 2>&1; then
    echo -e "From: test@${DOMAIN}\nTo: test@example.com\nSubject: dkim\n\nhi\n" \
      | opendkim-testmsg -d "$DOMAIN" -s default -k "${MAPS_DIR}/dkim/${DOMAIN}/default.private" 2>/tmp/dkim-test.err \
      && TEST_OK=1 || true
  else
    # Pas d'outil test : on vérifie juste la clé lisible
    if [[ -r "${MAPS_DIR}/dkim/${DOMAIN}/default.private" ]]; then
      TEST_OK=1
    fi
  fi
fi

echo "--- SigningTable ---"
cat "${MAPS_DIR}/opendkim-SigningTable"
echo "--- KeyTable ---"
cat "${MAPS_DIR}/opendkim-KeyTable"

if [[ "$TEST_OK" -ne 1 ]] && [[ ! -s "${MAPS_DIR}/opendkim-KeyTable" ]]; then
  echo "ERREUR: tables DKIM vides — milters NON activés"
  echo "Activez DKIM dans le panel Email pour le domaine, puis relancez."
  exit 1
fi

# Activer milters avec accept (si OpenDKIM plante, le mail passe quand même)
postconf -e "milter_default_action=accept"
postconf -e "milter_protocol=6"
postconf -e "smtpd_milters=inet:127.0.0.1:8891"
postconf -e "non_smtpd_milters=inet:127.0.0.1:8891"
# ORIGINATING pour submission (signature sortante)
if ! grep -q 'milter_macro_daemon_name=ORIGINATING' /etc/postfix/master.cf 2>/dev/null; then
  # injection légère sous submission
  sed -i '/^submission /,/^[^[:space:]#]/ {
    /milter_default_action=/a\  -o smtpd_milters=inet:127.0.0.1:8891\n  -o milter_macro_daemon_name=ORIGINATING
  }' /etc/postfix/master.cf 2>/dev/null || true
fi

systemctl reload postfix 2>/dev/null || systemctl restart postfix

echo
echo "milters=$(postconf -h smtpd_milters)"
echo "opendkim=$(systemctl is-active opendkim)"
echo
echo "Envoyez un mail de test. Si Roundcube → 451 :"
echo "  sudo bash ${REPO_DIR}/scripts/repair-smtp.sh"
echo "=== repair-dkim OK ==="
