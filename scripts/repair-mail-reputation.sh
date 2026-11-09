#!/usr/bin/env bash
# Répare la délivrabilité + hardening anti-Spamhaus CSS / DBL.
# SPF / DKIM / DMARC / PTR check / rate-limits / SMTP restrictions / PHP mail wrapper.
# Usage: sudo bash /opt/vzone-src/scripts/repair-mail-reputation.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-/var/lib/vzone/mail/maps}"

echo "=== repair-mail-reputation (0.40.31 / AngaPanel) ==="

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
  install -m 644 "${REPO_DIR}/deploy/postfix/main.cf" /etc/postfix/main.cf
  sed -i "s|__HOSTNAME__|${HOSTNAME_FQDN}|g" /etc/postfix/main.cf
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/postfix/main.cf
fi
if [[ -f "${REPO_DIR}/deploy/postfix/master.cf" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/master.cf" /etc/postfix/master.cf
fi
if [[ -f "${REPO_DIR}/deploy/postfix/header_checks" ]]; then
  install -m 644 "${REPO_DIR}/deploy/postfix/header_checks" /etc/postfix/header_checks
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

# Wrapper PHP mail() rate-limité (anti CSS)
if [[ -f "${REPO_DIR}/scripts/vzone-php-sendmail.sh" ]]; then
  install -m 755 "${REPO_DIR}/scripts/vzone-php-sendmail.sh" /usr/local/sbin/vzone-php-sendmail
  mkdir -p /var/lib/vzone/php-mail /var/log/vzone
  chmod 1777 /var/lib/vzone/php-mail
  # php.ini CLI / mods-available (best-effort)
  for ini in /etc/php/*/cli/php.ini /etc/php/*/fpm/php.ini; do
    [[ -f "$ini" ]] || continue
    if grep -q '^sendmail_path' "$ini" 2>/dev/null; then
      sed -i 's|^sendmail_path\s*=.*|sendmail_path = /usr/local/sbin/vzone-php-sendmail -t -i|' "$ini"
    else
      echo 'sendmail_path = /usr/local/sbin/vzone-php-sendmail -t -i' >> "$ini"
    fi
  done
fi

# SMTP Restrictions ON (bloque sorties tcp/25 hors Postfix)
if [[ -f "${REPO_DIR}/scripts/vzone-smtp-restrictions.sh" ]]; then
  install -m 755 "${REPO_DIR}/scripts/vzone-smtp-restrictions.sh" /usr/local/sbin/vzone-smtp-restrictions
  /usr/local/sbin/vzone-smtp-restrictions --enable || true
  echo "[smtp] SMTP Restrictions activées (OUTPUT tcp/25)"
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
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {md.name}: {exc}")

write_mail_maps()
print("maps OK (incl. sender_login)")
PY

# Permissions OpenDKIM
if [[ -d "${MAPS_DIR}/dkim" ]]; then
  chgrp -R opendkim "${MAPS_DIR}/dkim" 2>/dev/null || true
  chmod -R g+rX "${MAPS_DIR}/dkim" 2>/dev/null || true
  find "${MAPS_DIR}/dkim" -type f -name '*.private' -exec chmod 640 {} \; 2>/dev/null || true
fi
if [[ -f /etc/opendkim/KeyTable ]]; then
  chown opendkim:opendkim /etc/opendkim/KeyTable /etc/opendkim/SigningTable 2>/dev/null || true
  chmod 640 /etc/opendkim/KeyTable /etc/opendkim/SigningTable 2>/dev/null || true
fi

# postmap sender_login
[[ -f "${MAPS_DIR}/sender_login" ]] || touch "${MAPS_DIR}/sender_login"
postmap "${MAPS_DIR}/sender_login" 2>/dev/null || true
postmap "${MAPS_DIR}/virtual_mailboxes" 2>/dev/null || true
postmap "${MAPS_DIR}/valiases" 2>/dev/null || true
postmap "${MAPS_DIR}/vdomains" 2>/dev/null || true

# Appliquer rate-limits même si main.cf partiel
postconf -e \
  "smtpd_banner=\$myhostname ESMTP AngaPanel" \
  "smtpd_sender_login_maps=hash:${MAPS_DIR}/sender_login" \
  "header_checks=regexp:/etc/postfix/header_checks" \
  "anvil_rate_time_unit=60s" \
  "smtpd_client_connection_count_limit=20" \
  "smtpd_client_connection_rate_limit=30" \
  "smtpd_client_message_rate_limit=60" \
  "smtpd_client_recipient_rate_limit=120" \
  "smtpd_client_auth_rate_limit=15" \
  "default_destination_concurrency_limit=8" \
  "default_destination_rate_delay=1s" \
  "smtp_destination_concurrency_limit=5" \
  "smtp_destination_recipient_limit=25" \
  "smtpd_error_sleep_time=5s" \
  "smtpd_soft_error_limit=5" \
  "smtpd_hard_error_limit=10" \
  "disable_vrfy_command=yes" \
  "mynetworks=127.0.0.0/8 [::1]/128" \
  2>/dev/null || true

systemctl enable --now opendkim postfix 2>/dev/null || true
systemctl reload opendkim 2>/dev/null || systemctl restart opendkim
systemctl reload postfix 2>/dev/null || systemctl restart postfix

# Agent reload
if [[ -f "${REPO_DIR}/scripts/vzone-mail-reload.sh" ]]; then
  install -m 755 "${REPO_DIR}/scripts/vzone-mail-reload.sh" /usr/local/sbin/vzone-mail-reload
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-mail-reload.service" /etc/systemd/system/vzone-mail-reload.service
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-mail-reload.path" /etc/systemd/system/vzone-mail-reload.path
  systemctl daemon-reload
  systemctl enable --now vzone-mail-reload.path
  /usr/local/sbin/vzone-mail-reload || true
fi

# OpenDKIM daemon + sync conf
if [[ -f "${REPO_DIR}/deploy/opendkim/opendkim.conf" ]]; then
  mkdir -p /etc/opendkim/keys
  install -m 644 "${REPO_DIR}/deploy/opendkim/opendkim.conf" /etc/opendkim.conf
  touch "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable"
  touch /etc/opendkim/KeyTable /etc/opendkim/SigningTable
  chgrp opendkim "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true
  chmod 640 "${MAPS_DIR}/opendkim-KeyTable" "${MAPS_DIR}/opendkim-SigningTable" 2>/dev/null || true
  systemctl restart opendkim 2>/dev/null || true
fi

if [[ -f "${REPO_DIR}/scripts/repair-dkim.sh" ]] && [[ -s "${MAPS_DIR}/opendkim-KeyTable" ]]; then
  echo "[dkim] activation milter sortant…"
  bash "${REPO_DIR}/scripts/repair-dkim.sh" || echo "[warn] repair-dkim a échoué — SMTP reste OK sans signature"
fi

if [[ -f "${REPO_DIR}/deploy/systemd/vzone-smtp-guard.timer" ]]; then
  sed "s|/opt/vzone-src|${REPO_DIR}|g" \
    "${REPO_DIR}/deploy/systemd/vzone-smtp-guard.service" > /etc/systemd/system/vzone-smtp-guard.service
  install -m 644 "${REPO_DIR}/deploy/systemd/vzone-smtp-guard.timer" /etc/systemd/system/vzone-smtp-guard.timer
  chmod 755 "${REPO_DIR}/scripts/vzone-smtp-guard.sh"
  systemctl daemon-reload
  systemctl enable --now vzone-smtp-guard.timer 2>/dev/null || true
fi

# Fail2ban jails mail
if [[ -f "${REPO_DIR}/deploy/fail2ban/jail.d/vzone-mail.conf" ]] && [[ -d /etc/fail2ban/jail.d ]]; then
  install -m 644 "${REPO_DIR}/deploy/fail2ban/jail.d/vzone-mail.conf" /etc/fail2ban/jail.d/vzone-mail.conf
  systemctl reload fail2ban 2>/dev/null || true
fi

# Helper check
if [[ -f "${REPO_DIR}/scripts/vzone-mail-reputation-check.sh" ]]; then
  install -m 755 "${REPO_DIR}/scripts/vzone-mail-reputation-check.sh" /usr/local/sbin/vzone-mail-reputation-check
fi

echo "=== repair-mail-reputation OK ==="
echo
if [[ -x /usr/local/sbin/vzone-mail-reputation-check ]]; then
  /usr/local/sbin/vzone-mail-reputation-check || true
fi

echo
echo "[PTR / rDNS] — OBLIGATOIRE chez l'hébergeur (Contabo / OVH / Hetzner) :"
echo "  IP ${PUBLIC_IP} → $(hostname -f 2>/dev/null || hostname)"
echo "  Vérif: dig -x ${PUBLIC_IP} +short"
echo
echo "=== Suite ==="
echo "1) PTR aligné sur le hostname FQDN"
echo "2) SPF/DKIM/DMARC propagés (dig TXT domaine)"
echo "3) Test: https://www.mail-tester.com"
echo "4) Si listé: https://check.spamhaus.org/ — corriger puis delist"
echo "5) Audit: sudo vzone-mail-reputation-check"
