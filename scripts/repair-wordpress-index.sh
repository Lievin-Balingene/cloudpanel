#!/usr/bin/env bash
# Retire index.html « Site prêt » qui masque WordPress (index.php).
# Usage: sudo bash /opt/vzone-src/scripts/repair-wordpress-index.sh [username]
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
USER_FILTER="${1:-}"

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-vzone.settings.production}"
cd "${VZONE_ROOT}/backend"

echo "=== repair-wordpress-index ==="
"${VZONE_ROOT}/backend/.venv/bin/python" manage.py shell <<PY
from apps.accounts.models import User
from apps.wordpress.services import repair_wordpress_frontends
from apps.domains.services import refresh_web_routing

user = None
filt = """${USER_FILTER}""".strip()
if filt:
    user = User.objects.filter(username=filt).first()
    if not user:
        print(f"Utilisateur inconnu: {filt}")
        raise SystemExit(1)

n = repair_wordpress_frontends(user)
print(f"Sites corrigés (index.html retiré): {n}")
try:
    refresh_web_routing()
    print("Routing web rafraîchi (nginx/OLS).")
except Exception as e:
    print(f"refresh_web_routing: {e}")
PY
