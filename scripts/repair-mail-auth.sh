#!/usr/bin/env bash
# Répare l'auth Roundcube / Dovecot après création de boîtes email.
# Usage: sudo bash /opt/vzone-src/scripts/repair-mail-auth.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${VZONE_DATA_ROOT:-/var/lib/vzone}"
MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-${DATA_ROOT}/mail/maps}"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-/opt/vzone/roundcube}"

echo "=== repair-mail-auth (0.25.1) ==="

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi
MAPS_DIR="${VZONE_MAIL_MAPS_DIR:-$MAPS_DIR}"
DATA_ROOT="${VZONE_DATA_ROOT:-$DATA_ROOT}"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-$RC_ROOT}"

# --- Sync code ---
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

# --- Compte vmail + droits ---
mkdir -p /var/mail/vhosts "$MAPS_DIR"
id vmail >/dev/null 2>&1 || {
  groupadd -g 5000 vmail
  useradd -u 5000 -g vmail -d /var/mail/vhosts -s /usr/sbin/nologin -r vmail
}
usermod -aG vmail vzone 2>/dev/null || true
usermod -aG www-data vzone 2>/dev/null || true
chown -R vmail:vmail /var/mail/vhosts
chmod 2770 /var/mail/vhosts
chown -R vzone:vmail "${DATA_ROOT}/mail" 2>/dev/null || true
chmod -R g+rwX "${DATA_ROOT}/mail" 2>/dev/null || true

# --- SSO Roundcube ---
SSO_DIR="${VZONE_ROUNDCUBE_SSO_DIR:-${DATA_ROOT}/roundcube/sso}"
mkdir -p "$SSO_DIR"
chown vzone:www-data "$SSO_DIR"
chmod 2770 "$SSO_DIR"

# --- Env IMAPS local ---
touch "$ENV_FILE"
grep -q '^VZONE_MAIL_HOME_ROOT=' "$ENV_FILE" 2>/dev/null \
  || echo "VZONE_MAIL_HOME_ROOT=/var/mail/vhosts" >> "$ENV_FILE"
if grep -q '^VZONE_ROUNDCUBE_IMAP_HOST=' "$ENV_FILE" 2>/dev/null; then
  sed -i 's|^VZONE_ROUNDCUBE_IMAP_HOST=.*|VZONE_ROUNDCUBE_IMAP_HOST=ssl://127.0.0.1:993|' "$ENV_FILE"
else
  echo "VZONE_ROUNDCUBE_IMAP_HOST=ssl://127.0.0.1:993" >> "$ENV_FILE"
fi

# --- Réinstaller conf Dovecot ---
if [[ -d "${REPO_DIR}/deploy/dovecot" ]]; then
  echo "[dovecot] réinstallation conf…"
  install -m 644 "${REPO_DIR}/deploy/dovecot/dovecot.conf" /etc/dovecot/dovecot.conf
  install -m 644 "${REPO_DIR}/deploy/dovecot/10-auth.conf" /etc/dovecot/conf.d/10-auth.conf
  install -m 644 "${REPO_DIR}/deploy/dovecot/10-mail.conf" /etc/dovecot/conf.d/10-mail.conf
  install -m 644 "${REPO_DIR}/deploy/dovecot/10-master.conf" /etc/dovecot/conf.d/10-master.conf
  install -m 644 "${REPO_DIR}/deploy/dovecot/10-ssl.conf" /etc/dovecot/conf.d/10-ssl.conf
  install -m 644 "${REPO_DIR}/deploy/dovecot/auth-passwdfile.conf.ext" /etc/dovecot/conf.d/auth-passwdfile.conf.ext
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/dovecot/conf.d/auth-passwdfile.conf.ext
  sed -i "s|__MAPS_DIR__|${MAPS_DIR}|g" /etc/dovecot/conf.d/10-mail.conf
fi

# --- Roundcube : SSO PHP + imap_host (sans écraser DSN/DES_KEY) ---
if [[ -d "$RC_ROOT" && -f "${REPO_DIR}/deploy/roundcube/vzone-sso.php" ]]; then
  echo "[roundcube] mise à jour SSO + imap_host…"
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

# --- Rehash mots de passe depuis secrets + republier maps ---
set -a; source "$ENV_FILE"; set +a
export DJANGO_SETTINGS_MODULE=vzone.settings.production
echo "[django] rehash + write_mail_maps…"
"${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY'
from apps.email.models import Mailbox
from apps.email.passwd import hash_password, verify_password
from apps.email.services import write_mail_maps
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
        print(f"  · {box.address}: pas de secret → skip (reset MDP dans le panel)")
        n_skip += 1
        continue
    box.password_hash = hash_password(plain)
    box.save(update_fields=["password_hash", "updated_at"])
    n_ok += 1
    print(f"  ✓ {box.address}: hash mis à jour")

root = write_mail_maps()
p = Path(root) / "dovecot-users"
text = p.read_text(encoding="utf-8") if p.exists() else ""
print("maps:", root)
print("dovecot-users lines:", len(text.splitlines()) if text else 0)
for line in text.splitlines()[:8]:
    parts = line.split(":")
    if len(parts) >= 2:
        print(f"  {parts[0]}:***:{':'.join(parts[2:6])}")
    else:
        print(f"  {line[:80]}")
print(f"rehash ok={n_ok} skip={n_skip}")
PY

chgrp vmail "${MAPS_DIR}/dovecot-users" 2>/dev/null || true
chmod 640 "${MAPS_DIR}/dovecot-users" 2>/dev/null || true
chmod g+r "${MAPS_DIR}/dovecot-users" 2>/dev/null || true
find /var/mail/vhosts -type d -exec chown vmail:vmail {} \; 2>/dev/null || true
find /var/mail/vhosts -type d -exec chmod 770 {} \; 2>/dev/null || true

systemctl enable --now dovecot 2>/dev/null || true
systemctl restart dovecot
systemctl reload postfix 2>/dev/null || true
sleep 1

echo
echo "[tests]"
systemctl is-active dovecot || true
ls -la "${MAPS_DIR}/dovecot-users" || true
ss -tlnp 2>/dev/null | grep -E ':143|:993|:587' || true

if command -v doveadm >/dev/null 2>&1; then
  echo
  echo "[doveadm auth test] (secrets panel)…"
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY'
import subprocess
from apps.email.models import Mailbox

for box in Mailbox.objects.filter(is_active=True, is_suspended=False)[:20]:
    plain = ""
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
    print(f"  {status} {box.address}: {out[:200]}")
PY
fi

TARGET="info@7une.info"
if grep -q "^${TARGET}:" "${MAPS_DIR}/dovecot-users" 2>/dev/null; then
  echo
  echo "[info@7une.info] présent dans dovecot-users"
  doveadm user "$TARGET" 2>&1 | head -n 25 || true
else
  echo
  echo "[info@7une.info] ABSENT des maps — créez/réactivez la boîte dans le panel"
fi

echo
echo "=== Suite ==="
echo "1) Si doveadm auth FAIL → réinitialisez le MDP de la boîte dans le panel, puis relancez ce script"
echo "2) SSO : rouvrez le webmail depuis le panel (token 90s)"
echo "3) Login manuel Roundcube : adresse COMPLÈTE + MDP de la boîte (pas le compte panel)"
echo "4) Logs : journalctl -u dovecot -n 40 --no-pager"
echo "           tail -n 40 ${RC_ROOT}/logs/errors.log"
