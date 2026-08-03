#!/usr/bin/env bash
# Migre les homes vers /home/<username> (style cPanel) et synchronise l'env.
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_USER="${VZONE_USER:-vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
TARGET="/home"
OLD_CANDIDATES=(
  "/var/lib/vzone/homes"
  "/home/vzone/homes"
)

echo "[vzone] Migration homes → ${TARGET}/<username> (cPanel)"

mkdir -p "$TARGET"

# ACL pour que le panel puisse créer /home/<user>
if command -v setfacl >/dev/null 2>&1; then
  setfacl -m "u:${VZONE_USER}:rwx" "$TARGET" || true
  setfacl -d -m "u:${VZONE_USER}:rwx" "$TARGET" || true
fi
# Ne pas casser le /home système : 775 + groupe vzone seulement si pas déjà root-only multiuser
if [[ "$(stat -c '%U' "$TARGET" 2>/dev/null || echo root)" == "root" ]]; then
  # Ajoute ACL plutôt que chgrp agressif sur tout /home
  chmod 755 "$TARGET" 2>/dev/null || true
fi

migrate_tree() {
  local src="$1"
  [[ -d "$src" ]] || return 0
  echo "[vzone] Source détectée : $src"
  shopt -s nullglob
  for entry in "$src"/*; do
    [[ -e "$entry" ]] || continue
    local name
    name="$(basename "$entry")"
    # Ne pas déplacer des homes Linux système connus
    case "$name" in
      ubuntu|debian|ec2-user|centos|rocky|alma|vzone) continue ;;
    esac
    local dest="${TARGET}/${name}"
    if [[ -e "$dest" ]]; then
      echo "[vzone]  skip ${name} (existe déjà dans ${TARGET})"
      continue
    fi
    echo "[vzone]  mv ${entry} → ${dest}"
    mv "$entry" "$dest"
    chown -R "${VZONE_USER}:${VZONE_USER}" "$dest" 2>/dev/null || true
    chmod 755 "$dest" 2>/dev/null || true
  done
  shopt -u nullglob
  # Laisse un marqueur si vide
  rmdir "$src" 2>/dev/null || true
}

for old in "${OLD_CANDIDATES[@]}"; do
  migrate_tree "$old"
done

# Force env
if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^VZONE_HOME_ROOT=' "$ENV_FILE"; then
    sed -i 's|^VZONE_HOME_ROOT=.*|VZONE_HOME_ROOT=/home|' "$ENV_FILE"
  else
    echo "VZONE_HOME_ROOT=/home" >> "$ENV_FILE"
  fi
else
  mkdir -p "$(dirname "$ENV_FILE")"
  echo "VZONE_HOME_ROOT=/home" > "$ENV_FILE"
fi

# Home admin
mkdir -p "${TARGET}/admin"/{public_html/cgi-bin,mail,tmp,logs,etc,ssl,.trash,domains}
if [[ ! -e "${TARGET}/admin/www" ]]; then
  ln -sfn public_html "${TARGET}/admin/www"
fi
chown -R "${VZONE_USER}:${VZONE_USER}" "${TARGET}/admin"
chmod 755 "${TARGET}/admin"

# Recrée les homes manquants depuis la DB + met à jour home_directory
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  # shellcheck disable=SC1091
  set -a; source "$ENV_FILE"; set +a
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY'
from pathlib import Path
from django.conf import settings
from apps.accounts.models import User
from apps.accounts.services import provision_account_home

print("VZONE_HOME_ROOT =", settings.VZONE_HOME_ROOT)
root = Path(settings.VZONE_HOME_ROOT)
assert str(root) in ("/home", "/home/") or root == Path("/home"), settings.VZONE_HOME_ROOT

for u in User.objects.all().order_by("id"):
    try:
        home = provision_account_home(u)
        print(f"  OK {u.username} ({u.role}) → {home}")
    except Exception as exc:
        print(f"  ERR {u.username}: {exc}")
PY
fi

echo
echo "[vzone] Contenu de /home :"
ls -la /home || true
echo
echo "[vzone] Migration terminée. Redémarrez les services si besoin :"
echo "  systemctl restart vzone-api vzone-worker vzone-beat"
