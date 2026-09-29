#!/usr/bin/env bash
# Hotfix immédiat : runas GID + SQLite + deps (sans rebuild frontend).
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

mkdir -p "${VZONE_ROOT}/backend/apps/python_apps" "${VZONE_ROOT}/scripts"
rsync -a \
  "${REPO_DIR}/backend/apps/python_apps/services.py" \
  "${VZONE_ROOT}/backend/apps/python_apps/services.py"
rsync -a \
  "${REPO_DIR}/backend/apps/domains/vhosts.py" \
  "${VZONE_ROOT}/backend/apps/domains/vhosts.py" 2>/dev/null || true
rsync -a "${REPO_DIR}/VERSION" "${VZONE_ROOT}/VERSION"
rsync -a "${REPO_DIR}/scripts/vzone-runas.sh" "${VZONE_ROOT}/scripts/vzone-runas.sh"
rsync -a "${REPO_DIR}/scripts/vzone-fix-app-perms.sh" "${VZONE_ROOT}/scripts/vzone-fix-app-perms.sh"

# Critique : GID primaire (vzone-clients), pas le nom du user
install -m 755 "${REPO_DIR}/scripts/vzone-runas.sh" /usr/local/sbin/vzone-runas
install -m 755 "${REPO_DIR}/scripts/vzone-fix-app-perms.sh" /usr/local/sbin/vzone-fix-app-perms
bash "${REPO_DIR}/scripts/ensure-mkhome-sudoers.sh" || true

# Preuve runas corrigé
if grep -qE -- '--gid="\$USERNAME"' /usr/local/sbin/vzone-runas; then
  echo "ERREUR: /usr/local/sbin/vzone-runas utilise encore --gid=\$USERNAME" >&2
  exit 1
fi
if ! grep -q 'PRIMARY_GID' /usr/local/sbin/vzone-runas; then
  echo "ERREUR: PRIMARY_GID absent de vzone-runas" >&2
  exit 1
fi
echo "OK: vzone-runas utilise PRIMARY_GID"

if grep -q "SQLite toujours en lecture seule" "${VZONE_ROOT}/backend/apps/python_apps/services.py" 2>/dev/null; then
  echo "ERREUR: ancien message encore présent dans ${VZONE_ROOT}" >&2
  exit 1
fi
echo "OK: ancien message SQLite absent du code déployé"

# Groupe clients + membership
groupadd --system vzone-clients 2>/dev/null || true
if id -u "$USER_FILTER" >/dev/null 2>&1; then
  usermod -aG vzone-clients "$USER_FILTER" 2>/dev/null || true
  echo "user ${USER_FILTER} groups: $(id -nG "$USER_FILTER" 2>/dev/null || true)"
  echo "primary gid: $(id -g "$USER_FILTER") ($(id -gn "$USER_FILTER"))"
fi

# Test runas (pip / true)
if id -u "$USER_FILTER" >/dev/null 2>&1; then
  if /usr/local/sbin/vzone-runas "$USER_FILTER" -- /bin/true; then
    echo "OK: vzone-runas ${USER_FILTER} -- /bin/true"
  else
    echo "ERREUR: vzone-runas ${USER_FILTER} échoue encore" >&2
    /usr/local/sbin/vzone-runas "$USER_FILTER" -- /bin/true || true
  fi
fi

# Permissions compte
APP_DIR="${HOME_ROOT}/${USER_FILTER}/vzone"
CLIENTS_GROUP="${VZONE_CLIENTS_GROUP:-vzone-clients}"
if [[ -d "$APP_DIR" ]]; then
  echo "fix-app-perms --force ${USER_FILTER} ${APP_DIR}"
  /usr/local/sbin/vzone-fix-app-perms "$USER_FILTER" "$APP_DIR" --force || true
  chown -R "${USER_FILTER}:${CLIENTS_GROUP}" "$APP_DIR" 2>/dev/null \
    || chown -R "${USER_FILTER}:${USER_FILTER}" "$APP_DIR" 2>/dev/null || true
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

# Installer gunicorn/Django dans le venv si présent (via runas corrigé)
VENV_PY=""
shopt -s nullglob
for candidate in \
  "${HOME_ROOT}/${USER_FILTER}/virtualenv/"*"/"*"/bin/python" \
  "${APP_DIR}/.venv/bin/python" \
  "${HOME_ROOT}/${USER_FILTER}/vzone/.venv/bin/python"; do
  if [[ -x "$candidate" ]]; then
    VENV_PY="$candidate"
    break
  fi
done
shopt -u nullglob

if [[ -n "$VENV_PY" ]]; then
  echo "pip install gunicorn Django via ${VENV_PY}"
  /usr/local/sbin/vzone-runas "$USER_FILTER" -- \
    "$VENV_PY" -m pip install --upgrade pip gunicorn "Django>=4.2" 2>&1 | tail -n 30 \
    || echo "Avertissement: pip install a échoué (relancez Start dans le panel)"
else
  echo "Avertissement: venv python introuvable — Start panel fera ensure_runtime_deps"
fi

# Purge last_error en base
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/vzone/vzone.env 2>/dev/null || true
  set +a
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<PY || true
from apps.python_apps.models import PythonApp
n = PythonApp.objects.filter(last_error__icontains="SQLite").update(last_error="", status="stopped")
n2 = PythonApp.objects.filter(last_error__icontains="Failed to resolve group").update(last_error="", status="stopped")
n3 = PythonApp.objects.filter(last_error__icontains="Dépendances manquantes").update(last_error="", status="stopped")
print(f"last_error purgés: sqlite={n} group={n2} deps={n3}")
PY
fi

systemctl restart vzone-api vzone-worker 2>/dev/null || true
sleep 2
systemctl is-active vzone-api || true

echo "VERSION déployée=$(tr -d '[:space:]' < ${VZONE_ROOT}/VERSION 2>/dev/null || echo '?')"
echo "=== Fait. Dans le panel : Restart l'app Python. ==="
