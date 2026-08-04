#!/usr/bin/env bash
# Répare l'auth Roundcube / Dovecot après création de boîtes email.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${VZONE_DATA_ROOT:-/var/lib/vzone}"
MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-${DATA_ROOT}/mail/maps}"

echo "=== repair-mail-auth ==="

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi
MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-$MAPS_DIR}"

# Sync code email
if [[ -d "${REPO_DIR}/backend/apps/email" ]]; then
  rsync -a --exclude '__pycache__' --exclude '*.pyc' \
    "${REPO_DIR}/backend/apps/email/" "${VZONE_ROOT}/backend/apps/email/"
fi
if [[ -f "${REPO_DIR}/backend/vzone/settings/base.py" ]]; then
  rsync -a "${REPO_DIR}/backend/vzone/settings/base.py" \
    "${VZONE_ROOT}/backend/vzone/settings/base.py"
fi

# Droits stockage
mkdir -p /var/mail/vhosts "$MAPS_DIR"
id vmail >/dev/null 2>&1 || { groupadd -g 5000 vmail; useradd -u 5000 -g vmail -d /var/mail/vhosts -s /usr/sbin/nologin -r vmail; }
usermod -aG vmail vzone 2>/dev/null || true
usermod -aG www-data vzone 2>/dev/null || true
chown -R vmail:vmail /var/mail/vhosts
chmod 2770 /var/mail/vhosts
chown -R vzone:vmail "${DATA_ROOT}/mail" 2>/dev/null || true
chmod -R g+rwX "${DATA_ROOT}/mail" 2>/dev/null || true
chmod 640 "${MAPS_DIR}/dovecot-users" 2>/dev/null || true
chgrp vmail "${MAPS_DIR}/dovecot-users" 2>/dev/null || true

# SSO Roundcube
SSO_DIR="${VZONE_ROUNDCUBE_SSO_DIR:-${DATA_ROOT}/roundcube/sso}"
mkdir -p "$SSO_DIR"
chown vzone:www-data "$SSO_DIR"
chmod 2770 "$SSO_DIR"

# Env
grep -q '^VZONE_MAIL_HOME_ROOT=' "$ENV_FILE" 2>/dev/null \
  || echo "VZONE_MAIL_HOME_ROOT=/var/mail/vhosts" >> "$ENV_FILE"
if grep -q '^VZONE_ROUNDCUBE_IMAP_HOST=' "$ENV_FILE" 2>/dev/null; then
  sed -i 's|^VZONE_ROUNDCUBE_IMAP_HOST=.*|VZONE_ROUNDCUBE_IMAP_HOST=127.0.0.1:143|' "$ENV_FILE"
else
  echo "VZONE_ROUNDCUBE_IMAP_HOST=127.0.0.1:143" >> "$ENV_FILE"
fi

# Republier maps + migrer maildirs
set -a; source "$ENV_FILE"; set +a
export DJANGO_SETTINGS_MODULE=vzone.settings.production
"${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY'
from apps.email.services import write_mail_maps
root = write_mail_maps()
print("maps:", root)
from pathlib import Path
p = Path(root) / "dovecot-users"
print("dovecot-users lines:", len(p.read_text(encoding="utf-8").splitlines()) if p.exists() else 0)
print(p.read_text(encoding="utf-8")[:500] if p.exists() else "(absent)")
PY

chgrp vmail "${MAPS_DIR}/dovecot-users" 2>/dev/null || true
chmod 640 "${MAPS_DIR}/dovecot-users" 2>/dev/null || true
# Maildirs
find /var/mail/vhosts -type d -exec chown vmail:vmail {} \; 2>/dev/null || true
find /var/mail/vhosts -type d -exec chmod 770 {} \; 2>/dev/null || true

systemctl reload dovecot 2>/dev/null || systemctl restart dovecot
systemctl reload postfix 2>/dev/null || true

echo
echo "[tests]"
echo "  dovecot-users:"
ls -la "${MAPS_DIR}/dovecot-users" || true
echo "  sample users:"
cut -d: -f1 "${MAPS_DIR}/dovecot-users" 2>/dev/null | head -n 10 || true
if command -v doveadm >/dev/null 2>&1; then
  FIRST="$(cut -d: -f1 "${MAPS_DIR}/dovecot-users" 2>/dev/null | head -n1 || true)"
  if [[ -n "$FIRST" ]]; then
    echo "  doveadm user ${FIRST}:"
    doveadm user "$FIRST" 2>&1 | head -n 20 || true
  fi
fi
ss -tlnp | grep -E ':143|:587' || true

echo
echo "=== Suite ==="
echo "1) Roundcube : connectez-vous avec l'adresse COMPLÈTE (ex: info@7une.info) + mot de passe"
echo "2) Test auth : doveadm auth test 'info@domaine.tld' 'motdepasse'"
echo "3) Relancez SSO depuis le panel après reset MDP si besoin"
