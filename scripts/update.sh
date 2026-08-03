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

# (Ré)installe les unités systemd + nginx — utile après une install partielle
install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-api.service" /etc/systemd/system/
install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-worker.service" /etc/systemd/system/
install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-beat.service" /etc/systemd/system/
install -m 644 "${VZONE_ROOT}/deploy/nginx/vzone.conf" /etc/nginx/sites-available/vzone 2>/dev/null \
  || install -m 644 "${VZONE_ROOT}/deploy/nginx/vzone.conf" /etc/nginx/conf.d/vzone.conf
if [[ -d /etc/nginx/sites-enabled ]]; then
  ln -sfn /etc/nginx/sites-available/vzone /etc/nginx/sites-enabled/vzone
  rm -f /etc/nginx/sites-enabled/default
fi
nginx -t

systemctl daemon-reload
systemctl enable --now redis-server 2>/dev/null || systemctl enable --now redis 2>/dev/null || true
systemctl enable --now vzone-api vzone-worker vzone-beat nginx
systemctl reload nginx || systemctl restart nginx
echo "[vzone] Mise à jour terminée — version ${VERSION}"
echo "[vzone] Services : $(systemctl is-active vzone-api vzone-worker vzone-beat nginx | tr '\n' ' ')"
