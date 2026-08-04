#!/usr/bin/env bash
# Répare un panel en 404 (frontend/dist manquant ou build cassé).
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
REPO_DIR="${REPO_DIR:-/opt/vzone-src}"
[[ -d "$VZONE_ROOT" ]] || { echo "Introuvable: $VZONE_ROOT"; exit 1; }

echo "[vzone] Réparation frontend → ${VZONE_ROOT}/frontend/dist"

# Resync sources sans toucher node_modules / dist existant tant que le build n'est pas prêt
if [[ -d "${REPO_DIR}/frontend" ]]; then
  rsync -a \
    --exclude node_modules \
    --exclude dist \
    "${REPO_DIR}/frontend/" "${VZONE_ROOT}/frontend/"
fi

cd "${VZONE_ROOT}/frontend"
npm ci || npm install
npm run build

if [[ ! -f "${VZONE_ROOT}/frontend/dist/index.html" ]]; then
  echo "[vzone] ÉCHEC: index.html toujours absent après build" >&2
  exit 1
fi

chmod -R a+rX "${VZONE_ROOT}/frontend/dist"
chown -R root:www-data "${VZONE_ROOT}/frontend/dist" 2>/dev/null || true

# Backend + migration (souvent la cause du plantage mid-update)
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/vzone/vzone.env
  set +a
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" migrate --noinput || true
fi

systemctl restart vzone-api 2>/dev/null || true
if [[ -f "${REPO_DIR}/scripts/ensure-nginx.sh" ]]; then
  bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf" || systemctl reload nginx || true
else
  systemctl reload nginx || systemctl restart nginx || true
fi

echo "[vzone] OK — testez: ls -la ${VZONE_ROOT}/frontend/dist/index.html"
echo "[vzone] Puis rechargez le panel (Ctrl+F5)."
