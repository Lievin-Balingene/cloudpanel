#!/usr/bin/env bash
# Repare l'auth Roundcube / Dovecot (UNAVAILABLE = maps souvent illisibles).
# Usage: sudo bash /opt/vzone-src/scripts/repair-mail-auth.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${VZONE_DATA_ROOT:-/var/lib/vzone}"
MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-${DATA_ROOT}/mail/maps}"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-/opt/vzone/roundcube}"
DOVECOT_USERS_PUB="/etc/dovecot/vzone-users"

echo "=== repair-mail-auth (0.25.2) ==="

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi
MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-$MAPS_DIR}"
DATA_ROOT="${VZONE_DATA_ROOT:-$DATA_ROOT}"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-$RC_ROOT}"

if [[ -d "${REPO_DIR}/backend/apps/email" ]]; then
  rsync -a --exclude '__pycache__' --exclude '*.pyc' \
    "${REPO_DIR}/backend/apps/email/" "${VZONE_ROOT}/backend/apps/email/"
fi
if [[ -f "${REPO_DIR}/backend/vzone/settings/base.py" ]]; then
  rsync -a "${REPO_DIR}/backend/vzone/settings/base.py" \
    "${VZONE_ROOT}/backend/vzone/settings/base.py"
fi
if [[ -f "${REPO_DIR}/VERSION" ]]; then
  cp -f "${REPO_DIR}/VERSION" "${VZONE_ROOT}/VERSION" 2>/dev/null || true
fi

mkdir -p /var/mail/vhosts "$MAPS_DIR"
id vmail >/dev/null 2>&1 || {
  groupadd -g 5000 vmail
  useradd -u 5000 -g vmail -d /var/mail/vhosts -s /usr/sbin/nologin -r vmail
}
usermod -aG vmail vzone 2>/dev/null || true
usermod -aG www-data vzone 2>/dev/null || true
chown -R vmail:vmail /var/mail/vhosts
chmod 2770 /var/mail/vhosts

chmod 755 "${DATA_ROOT}" 2>/dev/null || true
mkdir -p "${DATA_ROOT}/mail"
chown -R vzone:vmail "${DATA_ROOT}/mail" 2>/dev/null || true
chmod 750 "${DATA_ROOT}/mail" "$MAPS_DIR" 2>/dev/null || true
chmod -R g+rwX "${DATA_ROOT}/mail" 2>/dev/null || true

SSO_DIR="${VZONE_ROUNDCUBE_SSO_DIR:-${DATA_ROOT}/roundcube/sso}"
mkdir -p "$SSO_DIR"
chown vzone:www-data "$SSO_DIR"
chmod 2770 "$SSO_DIR"

touch "$ENV_FILE"
grep -q '^VZONE_MAIL_HOME_ROOT=' "$ENV_FILE" 2>/dev/null \
  || echo "VZONE_MAIL_HOME_ROOT=/var/mail/vhosts" >> "$ENV_FILE"
if grep -q '^VZONE_ROUNDCUBE_IMAP_HOST=' "$ENV_FILE" 2>/dev/null; then
  sed -i 's|^VZONE_ROUNDCUBE_IMAP_HOST=.*|VZONE_ROUNDCUBE_IMAP_HOST=ssl://127.0.0.1:993|' "$ENV_FILE"
else
  echo "VZONE_ROUNDCUBE_IMAP_HOST=ssl://127.0.0.1:993" >> "$ENV_FILE"
fi

if [[ -d "${REPO_DIR}/deploy/dovecot" ]]; then
  echo "[dovecot] reinstallation conf…"
  install -m 644 "${REPO_DIR}/deploy/dovecot/dovecot.conf" /etc/dovecot/dovecot.conf
  install -m 644 "${REPO_DIR}/deploy/dovecot/10-auth.conf" /etc/dovecot/conf.d/10-auth.conf
  install -m 644 "${REPO_DIR}/deploy/dovecot/10-mail.conf" /etc/dovecot/conf.d/10-mail.conf
  install -m 644 "${REPO_DIR}/deploy/dovecot/10-master.conf" /etc/dovecot/conf.d/10-master.conf
  install -m 644 "${REPO_DIR}/deploy/dovecot/10-ssl.conf" /etc/dovecot/conf.d/10-ssl.conf
  install -m 644 "${REPO_DIR}/deploy/dovecot/auth-passwdfile.conf.ext" /etc/dovecot/conf.d/auth-passwdfile.conf.ext
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/dovecot/conf.d/auth-passwdfile.conf.ext
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/dovecot/conf.d/10-mail.conf
fi

if [[ -d "$RC_ROOT" && -f "${REPO_DIR}/deploy/roundcube/vzone-sso.php" ]]; then
  echo "[roundcube] mise a jour SSO + imap_host…"
  if [[ -f "${RC_ROOT}/config/config.inc.php" ]]; then
    sed -i "s|\$config\['imap_host'\] = '.*'|\$config['imap_host'] = 'ssl://127.0.0.1:993'|" \
      "${RC_ROOT}/config/config.inc.php" || true
    if ! grep -q "imap_auth_type" "${RC_ROOT}/config/config.inc.php"; then
      sed -i "/imap_host/a \$config['imap_auth_type'] = 'LOGIN';" \
        "${RC_ROOT}/config/config.inc.php" || true
    fi
  fi
  install -m 644 "${REPO_DIR}/deploy/roundcube/vzone-sso.php" "${RC_ROOT}/vzone-sso.php"
  sed -i "s|__SSO_DIR__|${SSO_DIR}|g" "${RC_ROOT}/vzone-sso.php"
  chown -R www-data:www-data "${RC_ROOT}/temp" "${RC_ROOT}/logs" 2>/dev/null || true
fi

set -a; source "$ENV_FILE"; set +a
export DJANGO_SETTINGS_MODULE=vzone.settings.production
echo "[django] rehash + write_mail_maps…"
"${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY'
from apps.email.models import Mailbox
from apps.email.passwd import hash_password
from apps.email.services import write_mail_maps, publish_dovecot_users
from pathlib import Path

n_ok = n_skip = 0
for box in Mailbox.objects.filter(is_active=True):
    plain = ""
    try:
        plain = box.get_password_plain() or ""
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {box.address}: secret illisible ({exc})")
        n_skip += 1
        continue
    if not plain:
        print(f"  · {box.address}: pas de secret → skip (reset MDP panel)")
        n_skip += 1
        continue
    box.password_hash = hash_password(plain)
    box.save(update_fields=["password_hash", "updated_at"])
    n_ok += 1
    print(f"  ✓ {box.address}: hash mis a jour")

root = write_mail_maps()
src = Path(root) / "dovecot-users"
pub = publish_dovecot_users(src)
print("maps:", root)
print("published:", pub)
print("dovecot-users lines:", len(src.read_text(encoding="utf-8").splitlines()) if src.exists() else 0)
print(f"rehash ok={n_ok} skip={n_skip}")
PY

if [[ -f "${MAPS_DIR}/dovecot-users" ]]; then
  install -m 640 -o root -g vmail "${MAPS_DIR}/dovecot-users" "$DOVECOT_USERS_PUB"
fi
chgrp vmail "${MAPS_DIR}/dovecot-users" 2>/dev/null || true
chmod 640 "${MAPS_DIR}/dovecot-users" "$DOVECOT_USERS_PUB" 2>/dev/null || true
find /var/mail/vhosts -type d -exec chown vmail:vmail {} \; 2>/dev/null || true
find /var/mail/vhosts -type d -exec chmod 770 {} \; 2>/dev/null || true

systemctl enable --now dovecot 2>/dev/null || true
doveconf -n >/dev/null 2>&1 || { echo "doveconf KO"; doveconf -n 2>&1 | tail -n 30; exit 1; }
systemctl restart dovecot
systemctl reload postfix 2>/dev/null || true
sleep 1

echo
echo "[tests]"
systemctl is-active dovecot || true
grep -A3 'passdb' /etc/dovecot/conf.d/auth-passwdfile.conf.ext || true
ls -la "$DOVECOT_USERS_PUB" "${MAPS_DIR}/dovecot-users" 2>&1 || true
cut -d: -f1 "$DOVECOT_USERS_PUB" 2>/dev/null | head -n 15 || true
ss -tlnp 2>/dev/null | grep -E ':143|:993|:587' || true
journalctl -u dovecot -n 20 --no-pager 2>/dev/null | tail -n 20 || true

if command -v doveadm >/dev/null 2>&1; then
  echo
  echo "[doveadm auth test]…"
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY'
import subprocess
from apps.email.models import Mailbox

for box in Mailbox.objects.filter(is_active=True, is_suspended=False)[:20]:
    try:
        plain = box.get_password_plain() or ""
    except Exception:
        plain = ""
    if not plain:
        print(f"  SKIP {box.address} (no secret)")
        continue
    r = subprocess.run(
        ["doveadm", "auth", "test", box.address, plain],
        capture_output=True,
        text=True,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " | ")
    status = "PASS" if r.returncode == 0 else "FAIL"
    print(f"  {status} {box.address}: {out[:220]}")
PY
fi

TARGET="info@7une.info"
if grep -q "^${TARGET}:" "$DOVECOT_USERS_PUB" 2>/dev/null; then
  echo
  echo "[info@7une.info] present dans $DOVECOT_USERS_PUB"
  doveadm user "$TARGET" 2>&1 | head -n 25 || true
else
  echo
  echo "[info@7une.info] ABSENT des maps"
fi

echo
echo "=== Suite ==="
echo "1) Si doveadm auth PASS → rouvrez le webmail depuis le panel"
echo "2) Si FAIL → reset MDP boite dans le panel, puis relancez ce script"
