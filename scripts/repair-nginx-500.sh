#!/usr/bin/env bash
# Répare 500 nginx, conflits server_name panel, frontend manquant, accès IP.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
DOMAINS_DIR="${VZONE_NGINX_DOMAINS_DIR:-/var/lib/vzone/nginx/domains}"

if [[ -f "$ENV_FILE" ]]; then
  set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a
fi

PANEL_HOSTS="${VZONE_PANEL_HOSTNAMES:-vpanel.vzonecloud.co.uk}"
PANEL_HOSTS="${PANEL_HOSTS//,/ }"

echo "=== repair-nginx-500 ==="
echo "[1] Dernières erreurs nginx"
tail -n 20 /var/log/nginx/error.log 2>/dev/null || true

echo "[2] Supprimer vhosts domaine qui dupliquent le panel (conflit server_name)"
mkdir -p "$DOMAINS_DIR"
for h in ${PANEL_HOSTS} vpanel.vzonecloud.co.uk; do
  [[ -n "$h" ]] || continue
  safe="$(echo "$h" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]/_/g')"
  rm -fv "${DOMAINS_DIR}/${safe}.conf" 2>/dev/null || true
done
# Au cas où le nom de fichier diffère : chercher server_name panel
if [[ -d "$DOMAINS_DIR" ]]; then
  for f in "${DOMAINS_DIR}"/*.conf; do
    [[ -f "$f" ]] || continue
    [[ "$(basename "$f")" == ".keep.conf" ]] && continue
    for h in ${PANEL_HOSTS}; do
      if grep -qE "server_name[^;]*[[:space:]]${h}([[:space:;]]|$)" "$f" 2>/dev/null; then
        echo "  remove duplicate $f (contient $h)"
        rm -fv "$f"
      fi
    done
  done
fi

echo "[3] Éviter double include vzone (conf.d + sites-enabled)"
rm -fv /etc/nginx/conf.d/vzone.conf 2>/dev/null || true

echo "[4] Frontend dist"
if [[ ! -f "${VZONE_ROOT}/frontend/dist/index.html" ]]; then
  echo "  dist manquant — build depuis ${REPO_DIR}/frontend"
  mkdir -p "${VZONE_ROOT}/frontend"
  if [[ -d "${REPO_DIR}/frontend" ]]; then
    rsync -a --delete \
      --exclude node_modules \
      "${REPO_DIR}/frontend/" "${VZONE_ROOT}/frontend/"
  fi
  cd "${VZONE_ROOT}/frontend"
  if [[ -f package.json ]]; then
    npm ci || npm install
    npm run build
  else
    echo "ERREUR: pas de frontend à builder" >&2
    exit 1
  fi
fi
[[ -f "${VZONE_ROOT}/frontend/dist/index.html" ]] || {
  echo "ERREUR: build frontend a échoué (pas de dist/index.html)" >&2
  exit 1
}
chmod -R a+rX "${VZONE_ROOT}/frontend/dist"
echo "  OK ${VZONE_ROOT}/frontend/dist/index.html"

echo "[5] ensure-homes (ACL écriture panel)"
bash "${REPO_DIR}/scripts/ensure-homes.sh" || true

echo "[6] ensure-nginx"
bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf"

echo "[6] Vérifier conflits server_name"
if nginx -T 2>&1 | grep -i "conflicting server name"; then
  echo "  Encore des conflits — listing server_name vpanel :"
  nginx -T 2>/dev/null | grep -n "server_name" | grep -i vpanel || true
  ls -la "$DOMAINS_DIR" || true
  ls -la /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null || true
else
  echo "  Pas de conflit server_name"
fi

echo "[7] Services"
systemctl restart nginx
systemctl is-active nginx vzone-api || true

echo "[8] Tests"
IP="$(hostname -I | awk '{print $1}')"
for url in \
  "http://127.0.0.1/login" \
  "https://127.0.0.1/login" \
  "http://${IP}/login"
do
  code="$(curl -sk -o /dev/null -w "%{http_code}" --resolve "vpanel.vzonecloud.co.uk:80:127.0.0.1" "$url" 2>/dev/null || \
         curl -sk -o /dev/null -w "%{http_code}" "$url" || true)"
  echo "  $url → ${code}"
done
code="$(curl -sk -o /dev/null -w "%{http_code}" -H "Host: vpanel.vzonecloud.co.uk" http://127.0.0.1/login || true)"
echo "  Host vpanel → ${code}"

echo "=== Ouvrez http://${IP}/login ==="
echo "=== done ==="
