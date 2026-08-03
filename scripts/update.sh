#!/usr/bin/env bash
# Mise à jour de V-zone Panel
set -euo pipefail

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }
[[ -d "$VZONE_ROOT" ]] || { echo "Installation introuvable: $VZONE_ROOT"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${REPO_DIR}/VERSION")"

echo "[vzone] Mise à jour vers ${VERSION}"
systemctl stop vzone-api vzone-worker vzone-beat 2>/dev/null || true

rsync -a --delete \
  --exclude '.git' --exclude 'frontend/node_modules' --exclude 'backend/.venv' \
  --exclude '.env' --exclude '.data' --exclude '.logs' \
  "${REPO_DIR}/" "${VZONE_ROOT}/"

# shellcheck disable=SC1091
source "${VZONE_ROOT}/backend/.venv/bin/activate"
set -a; source /etc/vzone/vzone.env; set +a
export DJANGO_SETTINGS_MODULE=vzone.settings.production
pip install -r "${VZONE_ROOT}/backend/requirements/prod.txt"
cd "${VZONE_ROOT}/backend"
python manage.py migrate --noinput
python manage.py collectstatic --noinput
deactivate

cd "${VZONE_ROOT}/frontend"
npm ci || npm install
npm run build

# (Ré)installe les unités systemd — utile après une install partielle
install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-api.service" /etc/systemd/system/
install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-worker.service" /etc/systemd/system/
install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-beat.service" /etc/systemd/system/
# Droits .env : lisible par l'utilisateur système vzone (commandes manage.py)
if [[ -f /etc/vzone/vzone.env ]]; then
  chown root:vzone /etc/vzone/vzone.env
  chmod 640 /etc/vzone/vzone.env
fi

bash "${REPO_DIR}/scripts/ensure-homes.sh"
# Recharger env après migration éventuelle de VZONE_HOME_ROOT
set -a; source /etc/vzone/vzone.env; set +a

# Recrée les homes manquants pour tous les comptes (idempotent)
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY' || true
from apps.accounts.models import User
from apps.accounts.services import provision_account_home
for u in User.objects.all():
    try:
        provision_account_home(u)
    except Exception as exc:
        print(u.username, exc)
PY
fi

# Stack mail Postfix/Dovecot/OpenDKIM (idempotent)
if [[ -f "${REPO_DIR}/scripts/install-mail.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-mail.sh" || echo "[vzone] Avertissement: install-mail.sh a échoué"
fi

# phpMyAdmin + MariaDB + PHP-FPM
if [[ -f "${REPO_DIR}/scripts/install-phpmyadmin.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-phpmyadmin.sh" || echo "[vzone] Avertissement: install-phpmyadmin.sh a échoué"
fi

# Roundcube Webmail
if [[ -f "${REPO_DIR}/scripts/install-roundcube.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-roundcube.sh" || echo "[vzone] Avertissement: install-roundcube.sh a échoué"
fi

# Certbot / Let's Encrypt
if [[ -f "${REPO_DIR}/scripts/install-certbot.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-certbot.sh" || echo "[vzone] Avertissement: install-certbot.sh a échoué"
fi

bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf"

systemctl daemon-reload
systemctl enable --now redis-server 2>/dev/null || systemctl enable --now redis 2>/dev/null || true
systemctl enable --now vzone-api vzone-worker vzone-beat nginx
echo "[vzone] Mise à jour terminée — version ${VERSION}"
echo "[vzone] Services : $(systemctl is-active vzone-api vzone-worker vzone-beat nginx | tr '\n' ' ')"
