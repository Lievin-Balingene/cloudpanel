#!/usr/bin/env bash
# Répare le routage : domaines clients → public_html, panel → IP seulement.
# Corrige le bug « https://domaine/login » (SPA panel servie par défaut).
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOMAINS_DIR="${VZONE_NGINX_DOMAINS_DIR:-/var/lib/vzone/nginx/domains}"

echo "=== V-zone fix-site-routing ==="

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi

# S'assurer que le runtime a la conf nginx à jour
mkdir -p "${VZONE_ROOT}/deploy/nginx"
cp -a "${REPO_DIR}/deploy/nginx/vzone.conf" "${VZONE_ROOT}/deploy/nginx/vzone.conf"
# Sync code vhosts si besoin
if [[ -d "${REPO_DIR}/backend/apps/domains" ]]; then
  rsync -a --exclude '__pycache__' --exclude '*.pyc' \
    "${REPO_DIR}/backend/apps/domains/" "${VZONE_ROOT}/backend/apps/domains/" 2>/dev/null || true
fi

echo "[1] Panel hostnames: '${VZONE_PANEL_HOSTNAMES:-}' (doit être vide ou un FQDN panel dédié — JAMAIS un domaine client)"
# Retirer tout domaine client connu de PANEL_HOSTNAMES
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" && -f "$ENV_FILE" ]]; then
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  CLEAN="$("${VZONE_ROOT}/backend/.venv/bin/python" - <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vzone.settings.production")
import django
django.setup()
from apps.domains.models import Domain
raw = (os.environ.get("VZONE_PANEL_HOSTNAMES") or "").replace(",", " ").split()
client = {d.name.lower() for d in Domain.objects.all()}
keep = [h for h in raw if h.strip().lower() not in client]
print(",".join(keep))
PY
)" || CLEAN="${VZONE_PANEL_HOSTNAMES:-}"
  if [[ "${CLEAN}" != "${VZONE_PANEL_HOSTNAMES:-}" ]]; then
    echo "[1b] Nettoyage VZONE_PANEL_HOSTNAMES: '${VZONE_PANEL_HOSTNAMES:-}' → '${CLEAN}'"
    if grep -q '^VZONE_PANEL_HOSTNAMES=' "$ENV_FILE"; then
      sed -i "s|^VZONE_PANEL_HOSTNAMES=.*|VZONE_PANEL_HOSTNAMES=${CLEAN}|" "$ENV_FILE"
    else
      echo "VZONE_PANEL_HOSTNAMES=${CLEAN}" >> "$ENV_FILE"
    fi
    set -a; source "$ENV_FILE"; set +a
  fi
fi

echo "[2] Reinstall nginx (parking default + panel séparé)"
bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf"

echo "[3] Sync HTTPS / vhosts"
bash "${REPO_DIR}/scripts/ensure-https.sh" || true

echo "[4] Vhosts domaines"
ls -la "${DOMAINS_DIR}" 2>/dev/null || true

echo "[5] Tests"
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
echo "--- Host unknown → parking (pas /login) ---"
curl -sI -H "Host: unknown.invalid" http://127.0.0.1/ | head -n 8 || true
echo "--- Panel via IP ---"
curl -sI -H "Host: ${HOST_IP}" "http://127.0.0.1/login" | head -n 8 || true

for conf in "${DOMAINS_DIR}"/*.conf; do
  [[ -f "$conf" ]] || continue
  [[ "$(basename "$conf")" == ".keep.conf" ]] && continue
  DN="$(grep -m1 'server_name' "$conf" | awk '{print $2}' | tr -d ';')"
  [[ -z "$DN" || "$DN" == "_" ]] && continue
  echo "--- Domaine ${DN} ---"
  grep -E '^\s*(listen|server_name|root |return 301|ssl_certificate)' "$conf" | head -n 20
  BODY="$(curl -sk -H "Host: ${DN}" "http://127.0.0.1/" 2>/dev/null | head -c 400 || true)"
  CODE="$(curl -sk -o /dev/null -w '%{http_code}' -H "Host: ${DN}" "http://127.0.0.1/" || true)"
  echo "HTTP ${CODE} preview: ${BODY:0:180}"
  if echo "$BODY" | grep -qE '/assets/index-|V-zone</title>|<div id="root"'; then
    echo "[ERREUR] ${DN} sert encore la SPA panel !"
  elif echo "$BODY" | grep -qiE 'login|Sign in'; then
    # welcome html might not have login; SPA does
    if echo "$BODY" | grep -qi 'assets/index'; then
      echo "[ERREUR] ${DN} → panel login"
    else
      echo "[ok] ${DN} ne semble pas être la SPA"
    fi
  else
    echo "[ok] ${DN} ne semble pas être la SPA panel"
  fi
  # HTTPS si cert
  if [[ -f "/var/lib/vzone/ssl/${DN}/fullchain.pem" ]]; then
    HCODE="$(curl -sk -o /dev/null -w '%{http_code}' -H "Host: ${DN}" "https://127.0.0.1/" || true)"
    HBODY="$(curl -sk -H "Host: ${DN}" "https://127.0.0.1/" 2>/dev/null | head -c 200 || true)"
    echo "HTTPS ${HCODE} preview: ${HBODY:0:120}"
    if echo "$HBODY" | grep -qE '/assets/index-'; then
      echo "[ERREUR] HTTPS ${DN} = SPA panel"
    fi
  fi
done

echo "=== Terminé ==="
echo "Panel : http://${HOST_IP}/login  (ou hostname panel dédié)"
echo "Sites : http://votredomaine/ → ~/public_html (jamais /login)"
