#!/usr/bin/env bash
# Répare le 404 global du panel (dist OK mais nginx ne sert pas la SPA).
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
REPO_DIR="${REPO_DIR:-/opt/vzone-src}"
[[ -d "$REPO_DIR" ]] || REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== repair-panel-404 ==="

echo "[1] Frontend dist"
if [[ ! -f "${VZONE_ROOT}/frontend/dist/index.html" ]]; then
  bash "${REPO_DIR}/scripts/repair-frontend.sh"
fi
ls -la "${VZONE_ROOT}/frontend/dist/index.html"
sudo -u www-data test -r "${VZONE_ROOT}/frontend/dist/index.html" \
  && echo "  www-data: OK lit index.html" \
  || echo "  www-data: NE LIT PAS index.html"

echo "[2] Purge anciennes conf panel conflictuelles"
rm -fv /etc/nginx/sites-enabled/vzone \
       /etc/nginx/sites-available/vzone \
       /etc/nginx/conf.d/vzone.conf 2>/dev/null || true
# Autres default_server
for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
  [[ -e "$f" ]] || continue
  base="$(basename "$f")"
  [[ "$base" == "zz-vzone-panel.conf" ]] && continue
  [[ "$base" == "vzone-domains-include.conf" || "$base" == "vzone-map-upgrade.conf" ]] && continue
  if grep -q "default_server" "$f" 2>/dev/null; then
    echo "  disable $f"
    mv -f "$f" "${f}.disabled-by-vzone" 2>/dev/null || rm -fv "$f"
  fi
done

echo "[3] Réinstalle conf panel (conf.d/zz-vzone-panel.conf)"
bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf"

echo "[4] Vérification"
curl -sk -D- -o /tmp/vzone-login.body -H "Host: vpanel.vzonecloud.co.uk" "http://127.0.0.1/login" | head -n 15 || true
echo "--- body (200 premiers octets) ---"
head -c 200 /tmp/vzone-login.body; echo
if grep -qiE 'DOCTYPE|root|vite|V-zone|login' /tmp/vzone-login.body; then
  echo "[OK] SPA servie"
else
  echo "[ÉCHEC] Corps inattendu — dump nginx roots:"
  nginx -T 2>/dev/null | grep -E 'listen |server_name |root |default_server|try_files|zz-vzone' | head -80
  exit 1
fi

echo "=== Terminé — Ctrl+F5 sur https://vpanel.vzonecloud.co.uk/login ==="
