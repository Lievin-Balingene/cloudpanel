#!/usr/bin/env bash
# Répare permissions SQLite + resync vhosts pour toutes les apps Python.
# Usage: sudo bash scripts/repair-python-apps.sh [username]
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
FILTER_USER="${1:-}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
fi

echo "=== repair-python-apps ==="

# (Ré)installe helper + sudoers
if [[ -f "${REPO_DIR}/scripts/ensure-mkhome-sudoers.sh" ]]; then
  bash "${REPO_DIR}/scripts/ensure-mkhome-sudoers.sh" || true
elif [[ -f "${VZONE_ROOT}/../vzone-src/scripts/ensure-mkhome-sudoers.sh" ]]; then
  bash "${VZONE_ROOT}/../vzone-src/scripts/ensure-mkhome-sudoers.sh" || true
fi

FIX="/usr/local/sbin/vzone-fix-app-perms"
if [[ ! -x "$FIX" ]]; then
  echo "ERREUR: $FIX absent" >&2
  exit 1
fi

# nginx reload agent (sinon vhosts écrits mais non appliqués)
if [[ -f "${REPO_DIR}/scripts/ensure-nginx-reload-agent.sh" ]]; then
  bash "${REPO_DIR}/scripts/ensure-nginx-reload-agent.sh" || true
fi

fixed=0
for home in "${HOME_ROOT}"/*; do
  [[ -d "$home" ]] || continue
  user="$(basename "$home")"
  [[ "$user" =~ ^[a-z][a-z0-9_-]{2,31}$ ]] || continue
  if [[ -n "$FILTER_USER" && "$user" != "$FILTER_USER" ]]; then
    continue
  fi
  # Corriger chaque dossier app potentiel (racine home + 1 niveau)
  while IFS= read -r -d '' db; do
    appdir="$(dirname "$db")"
    echo "[fix] $user → $appdir"
    "$FIX" "$user" "$appdir" --force || "$FIX" "$user" "$appdir" || echo "  avertissement: fix échoué pour $appdir"
    fixed=$((fixed + 1))
  done < <(find "$home" -maxdepth 4 -type f -name 'db.sqlite3' -print0 2>/dev/null)
  # Aussi passenger_wsgi.py sans sqlite encore
  while IFS= read -r -d '' wsgi; do
    appdir="$(dirname "$wsgi")"
    echo "[fix] $user → $appdir (wsgi)"
    "$FIX" "$user" "$appdir" --force || "$FIX" "$user" "$appdir" || true
    fixed=$((fixed + 1))
  done < <(find "$home" -maxdepth 3 -type f -name 'passenger_wsgi.py' -print0 2>/dev/null)
done

echo "[django] reconcile + rewrite Hello stubs + refresh vhosts"
cd "${VZONE_ROOT}/backend" 2>/dev/null || cd "${REPO_DIR}/backend"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python manage.py reconcile_python_apps 2>/dev/null || true
  .venv/bin/python - <<'PY' 2>/dev/null || true
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vzone.settings.production")
django.setup()
from apps.domains.services import refresh_web_routing
from apps.python_apps.models import PythonApp
from apps.python_apps.services import (
    absolute_app_root,
    fix_client_paths,
    is_passenger_hello_stub,
    restart_python_app,
    sync_passenger_wsgi,
)
n = 0
rewrote = 0
restarted = []
for app in PythonApp.objects.exclude(status="removed").select_related("owner"):
    try:
        root = absolute_app_root(app)
        fix_client_paths(app.owner, root, required=False, verify_sqlite_in=root)
        n += 1
        entry = root / "passenger_wsgi.py"
        text = ""
        if entry.is_file():
            text = entry.read_text(encoding="utf-8", errors="replace")
        if is_passenger_hello_stub(text) or app.framework == "django":
            info = sync_passenger_wsgi(app, root, force=True)
            print("sync", app.name, info.get("settings_module"), "rewritten=", info.get("rewritten"))
            if info.get("rewritten") or is_passenger_hello_stub(text):
                rewrote += 1
                if app.status == "running":
                    try:
                        restart_python_app(app)
                        restarted.append(app.name)
                    except Exception as e:
                        print("restart fail", app.name, e)
    except Exception as e:
        print("skip", app.name, e)
print("apps fixed via ORM:", n, "wsgi rewrites:", rewrote, "restarted:", restarted)
refresh_web_routing()
print("vhosts refreshed")
PY
fi

systemctl reload nginx 2>/dev/null || systemctl start vzone-nginx-reload.service 2>/dev/null || true

echo "=== OK (${fixed} chemins touchés) ==="
echo "Redémarrez les apps Python depuis le panel (Start / Restart)."
if [[ -n "$FILTER_USER" ]]; then
  echo "Exemple: sudo $FIX $FILTER_USER /home/$FILTER_USER/vzone"
fi
