#!/usr/bin/env bash
# Hotfix immédiat : SQLite readonly + redéploiement code Python (sans rebuild frontend).
# Usage: sudo bash scripts/hotfix-python-sqlite.sh [username]
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }

USER_FILTER="${1:-une}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
HOME_ROOT="${VZONE_HOME_ROOT:-/home}"

echo "=== hotfix-python-sqlite ==="
echo "REPO=${REPO_DIR}"
echo "VZONE_ROOT=${VZONE_ROOT}"

cd "$REPO_DIR"
if [[ -d .git ]]; then
  git fetch origin main 2>/dev/null || git fetch origin 2>/dev/null || true
  git pull --ff-only origin main 2>/dev/null || git pull --ff-only 2>/dev/null || true
fi
echo "VERSION src=$(tr -d '[:space:]' < VERSION 2>/dev/null || echo '?')"

# Copie ciblée du code critique (même si update.sh complet a échoué)
mkdir -p "${VZONE_ROOT}/backend/apps/python_apps" "${VZONE_ROOT}/scripts"
rsync -a \
  "${REPO_DIR}/backend/apps/python_apps/services.py" \
  "${VZONE_ROOT}/backend/apps/python_apps/services.py"
rsync -a \
  "${REPO_DIR}/backend/apps/domains/vhosts.py" \
  "${VZONE_ROOT}/backend/apps/domains/vhosts.py" 2>/dev/null || true
rsync -a "${REPO_DIR}/VERSION" "${VZONE_ROOT}/VERSION"
install -m 755 "${REPO_DIR}/scripts/vzone-fix-app-perms.sh" /usr/local/sbin/vzone-fix-app-perms
bash "${REPO_DIR}/scripts/ensure-mkhome-sudoers.sh" || true

# Preuve : l'ancien message NE DOIT PLUS exister
if grep -q "SQLite toujours en lecture seule" "${VZONE_ROOT}/backend/apps/python_apps/services.py" 2>/dev/null; then
  echo "ERREUR: ancien message encore présent dans ${VZONE_ROOT} — rsync a échoué" >&2
  exit 1
fi
echo "OK: ancien message absent du code déployé"

# Permissions compte
APP_DIR="${HOME_ROOT}/${USER_FILTER}/vzone"
if [[ -d "$APP_DIR" ]]; then
  echo "fix-app-perms --force ${USER_FILTER} ${APP_DIR}"
  /usr/local/sbin/vzone-fix-app-perms "$USER_FILTER" "$APP_DIR" --force || true
  # Nuclear local si besoin
  chown -R "${USER_FILTER}:${USER_FILTER}" "$APP_DIR" 2>/dev/null || true
  chmod -R u+rwX,g+rwX,o+rX "$APP_DIR" 2>/dev/null || true
  find "$APP_DIR" -name 'db.sqlite3*' -exec chmod 666 {} \; 2>/dev/null || true
  ls -la "${APP_DIR}/db.sqlite3" 2>/dev/null || echo "(pas encore de db.sqlite3)"
else
  echo "Avertissement: ${APP_DIR} absent — cherche d'autres apps…"
  find "${HOME_ROOT}/${USER_FILTER}" -maxdepth 3 -name 'db.sqlite3' -print 2>/dev/null | while read -r db; do
    d="$(dirname "$db")"
    /usr/local/sbin/vzone-fix-app-perms "$USER_FILTER" "$d" --force || true
  done
fi

# Purge last_error en base (sinon l'UI réaffiche l'ancienne erreur)
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/vzone/vzone.env 2>/dev/null || true
  set +a
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<PY || true
from apps.python_apps.models import PythonApp
n = PythonApp.objects.filter(last_error__icontains="SQLite").update(last_error="", status="stopped")
print(f"last_error SQLite purgés: {n}")
n2 = PythonApp.objects.exclude(last_error="").filter(status="error").count()
print(f"apps encore en error avec last_error: {n2}")
PY
fi

# Recharge API (sinon ancien .pyc / process)
systemctl restart vzone-api vzone-worker 2>/dev/null || true
sleep 2
systemctl is-active vzone-api || true

echo "VERSION déployée=$(tr -d '[:space:]' < ${VZONE_ROOT}/VERSION 2>/dev/null || echo '?')"
echo "=== Fait. Dans le panel : Restart l'app Python. ==="
echo "Si l'erreur revient à l'identique, coller la sortie de :"
echo "  grep -n 'SQLite toujours' ${VZONE_ROOT}/backend/apps/python_apps/services.py || echo ABSENT"
echo "  systemctl status vzone-api --no-pager | head -20"
