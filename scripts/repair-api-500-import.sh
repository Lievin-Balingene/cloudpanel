#!/usr/bin/env bash
# Répare un 500 Daphne dû à un ImportError / migrate incomplet (ex. datetime.UTC sur Py3.10).
# Usage: sudo bash /opt/vzone-src/scripts/repair-api-500-import.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
REPO_DIR="${REPO_DIR:-/opt/vzone-src}"
ENV_FILE="${VZONE_ENV:-/etc/vzone/vzone.env}"

echo "[vzone] Repair API 500 (import / migrate)"

if [[ -d "${REPO_DIR}/.git" ]]; then
  git -C "${REPO_DIR}" fetch origin || true
  git -C "${REPO_DIR}" reset --hard origin/main || true
fi

# Sync code source → runtime (sans rebuild frontend complet)
if [[ -d "${REPO_DIR}/backend" ]]; then
  rsync -a --delete \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    "${REPO_DIR}/backend/" "${VZONE_ROOT}/backend/"
  [[ -f "${REPO_DIR}/VERSION" ]] && cp -f "${REPO_DIR}/VERSION" "${VZONE_ROOT}/VERSION"
fi

# shellcheck disable=SC1091
source "${VZONE_ROOT}/backend/.venv/bin/activate"
set -a; source "${ENV_FILE}"; set +a
export DJANGO_SETTINGS_MODULE=vzone.settings.production
cd "${VZONE_ROOT}/backend"

echo "[vzone] Test import URLconf…"
python -c "import django; django.setup(); from django.urls import get_resolver; get_resolver().url_patterns; print('URLconf OK')"

echo "[vzone] migrate…"
python manage.py migrate --noinput
deactivate

bash "${REPO_DIR}/scripts/ensure-vzone-api.sh" || bash "${VZONE_ROOT}/scripts/ensure-vzone-api.sh"

echo "[vzone] Repair API terminé — rechargez le panneau."
