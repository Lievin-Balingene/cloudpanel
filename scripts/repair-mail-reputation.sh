#!/usr/bin/env bash
# Répare la délivrabilité sortante : SPF / DKIM / DMARC / A mail. / OpenDKIM / BIND.
# Usage: sudo bash /opt/vzone-src/scripts/repair-mail-reputation.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== repair-mail-reputation (0.25.5) ==="

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi

# Sync code email + postfix
if [[ -d "${REPO_DIR}/backend/apps/email" ]]; then
  rsync -a --exclude '__pycache__' --exclude '*.pyc' \
    "${REPO_DIR}/backend/apps/email/" "${VZONE_ROOT}/backend/apps/email/"
fi
if [[ -f "${REPO_DIR}/deploy/postfix/main.cf" ]]; then
  HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"
  MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-/var/lib/vzone/mail/maps}"
  install -m 644 "${REPO_DIR}/deploy/postfix/main.cf" /etc/postfix/main.cf
  sed -i "s|__HOSTNAME__|${HOSTNAME_FQDN}|g" /etc/postfix/main.cf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/postfix/main.cf
fi

# IP publique pour SPF
PUBLIC_IP=""
PUBLIC_IP="$(curl -4 -fsS --max-time 5 https://ifconfig.me 2>/dev/null || true)"
if [[ -z "$PUBLIC_IP" ]]; then
  PUBLIC_IP="$(curl -4 -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
fi
if [[ -z "$PUBLIC_IP" ]]; then
  PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
echo "IP publique détectée: ${PUBLIC_IP:-?}"

touch "$ENV_FILE"
if [[ -n "$PUBLIC_IP" ]]; then
  if grep -q '^VZONE_MAIL_PUBLIC_IP=' "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^VZONE_MAIL_PUBLIC_IP=.*|VZONE_MAIL_PUBLIC_IP=${PUBLIC_IP}|" "$ENV_FILE"
  else
    echo "VZONE_MAIL_PUBLIC_IP=${PUBLIC_IP}" >> "$ENV_FILE"
  fi
  if grep -q '^VZONE_PUBLIC_IP=' "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^VZONE_PUBLIC_IP=.*|VZONE_PUBLIC_IP=${PUBLIC_IP}|" "$ENV_FILE"
  else
    echo "VZONE_PUBLIC_IP=${PUBLIC_IP}" >> "$ENV_FILE"
  fi
fi

# OpenDKIM TrustedHosts
if [[ -f /etc/opendkim/TrustedHosts ]]; then
  grep -qxF "$PUBLIC_IP" /etc/opendkim/TrustedHosts 2>/dev/null || echo "$PUBLIC_IP" >> /etc/opendkim/TrustedHosts
  HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"
  grep -qxF "$HOSTNAME_FQDN" /etc/opendkim/TrustedHosts 2>/dev/null || echo "$HOSTNAME_FQDN" >> /etc/opendkim/TrustedHosts
fi

set -a; source "$ENV_FILE"; set +a
export DJANGO_SETTINGS_MODULE=vzone.settings.production

echo "[django] ensure_mail_reputation pour tous les domaines…"
"${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY'
from apps.email.models import MailDomain
from apps.email.services import ensure_mail_reputation, write_mail_maps

for md in MailDomain.objects.filter(is_active=True):
    try:
        info = ensure_mail_reputation(md)
        print(f"  ✓ {md.name}: dkim={info.get('dkim')} spf={info.get('spf')}")
        if info.get("dkim_value") or info.get("dkim"):
            print(f"      dkim_dns={str(info.get('dkim'))[:60]}…")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {md.name}: {exc}")

write_mail_maps()
print("maps OK")
PY

# Permissions OpenDKIM
MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-/var/lib/vzone/mail/maps}"
if [[ -d "${MAPS_DIR}/dkim" ]]; then
  chgrp -R opendkim "${MAPS_DIR}/dkim" 2>/dev/null || true
  chmod -R g+rX "${MAPS_DIR}/dkim" 2>/dev/null || true
  find "${MAPS_DIR}/dkim" -type f -name '*.private' -exec chmod 640 {} \; 2>/dev/null || true
fi
if [[ -f /etc/opendkim/KeyTable ]]; then
  chown opendkim:opendkim /etc/opendkim/KeyTable /etc/opendkim/SigningTable 2>/dev/null || true
  chmod 640 /etc/opendkim/KeyTable /etc/opendkim/SigningTable 2>/dev/null || true
fi

systemctl enable --now opendkim postfix 2>/dev/null || true
systemctl reload opendkim 2>/dev/null || systemctl restart opendkim
systemctl reload postfix 2>/dev/null || systemctl restart postfix

echo
echo "[DNS public]"
for d in $( "${VZONE_ROOT}/backend/.venv/bin/python" -c \
  "import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','vzone.settings.production'); django.setup(); from apps.email.models import MailDomain; print(' '.join(MailDomain.objects.filter(is_active=True).values_list('name', flat=True)))" \
  2>/dev/null ); do
  echo "--- $d ---"
  dig +short TXT "$d" @127.0.0.1 2>/dev/null | head -n 5 || true
  dig +short TXT "default._domainkey.$d" @127.0.0.1 2>/dev/null | head -n 2 || true
  dig +short TXT "_dmarc.$d" @127.0.0.1 2>/dev/null | head -n 2 || true
  dig +short A "mail.$d" @127.0.0.1 2>/dev/null || true
  dig +short MX "$d" @127.0.0.1 2>/dev/null || true
done

echo
echo "[PTR / rDNS] — à configurer chez l'hébergeur (Contabo / VPS) :"
echo "  IP ${PUBLIC_IP} → $(hostname -f 2>/dev/null || hostname)"
echo "  Vérif: dig -x ${PUBLIC_IP} +short"
echo
echo "=== Suite ==="
echo "1) Attendez 1–5 min la propagation DNS"
echo "2) Test: https://www.mail-tester.com (envoyez un mail depuis Roundcube)"
echo "3) Vérifiez DKIM-Signature dans les en-têtes du message reçu"
echo "4) PTR manquant = spam fréquent même avec SPF/DKIM OK"
