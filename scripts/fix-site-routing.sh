#!/usr/bin/env bash
# Diagnostic + réparation du routage sites vs panel.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== V-zone fix-site-routing ==="

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi

echo "[1] Panel hostnames: ${VZONE_PANEL_HOSTNAMES:-<non défini>}"
echo "[2] nginx -t"
nginx -t || { echo "nginx -t ÉCHEC — arrêt"; exit 1; }

echo "[3] Reinstall nginx layout (parking + panel séparé)"
bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf"

echo "[4] Sync tous les vhosts domaines + HTTPS"
bash "${REPO_DIR}/scripts/ensure-https.sh" || true

echo "[5] Blocs server_name / default_server"
nginx -T 2>/dev/null | grep -E 'listen |server_name |root |ssl_certificate |default_server' | head -n 80

echo "[6] Fichiers vhosts domaines"
ls -la /var/lib/vzone/nginx/domains/ 2>/dev/null || true

echo "[7] Tests locaux"
PANEL="${VZONE_PANEL_HOSTNAMES:-vpanel.vzonecloud.co.uk}"
PANEL="${PANEL%%,*}"
PANEL="$(echo "$PANEL" | awk '{print $1}')"
curl -sI -H "Host: unknown.invalid" http://127.0.0.1/ | head -n 5 || true
echo "---"
curl -sI -H "Host: ${PANEL}" http://127.0.0.1/login | head -n 5 || true
echo "---"
# Premier domaine client trouvé
SAMPLE="$(ls /var/lib/vzone/nginx/domains/*.conf 2>/dev/null | grep -v keep | head -n1 || true)"
if [[ -n "$SAMPLE" ]]; then
  DN="$(basename "$SAMPLE" .conf | tr '_' '.')"
  # Meilleure extraction du server_name
  DN="$(grep -m1 'server_name' "$SAMPLE" | awk '{print $2}' | tr -d ';')"
  echo "Sample domain vhost: $SAMPLE → Host $DN"
  grep -E 'root |proxy_pass|server_name|listen' "$SAMPLE" | head -n 20
  curl -sI -H "Host: ${DN}" http://127.0.0.1/ | head -n 8 || true
  BODY="$(curl -s -H "Host: ${DN}" http://127.0.0.1/ | head -c 200 || true)"
  echo "Body preview: $BODY"
  if echo "$BODY" | grep -qi 'root\|login\|vzone\|Vite'; then
    if echo "$BODY" | grep -qi 'Document root V-zone\|<!DOCTYPE'; then
      echo "[ok] Ne semble pas être la SPA login"
    fi
  fi
  if echo "$BODY" | grep -q '/assets/index-'; then
    echo "[ERREUR] Le domaine sert encore le frontend panel (SPA) !"
  fi
fi

echo "=== Terminé ==="
echo "Panel : https://${PANEL}/login"
echo "Sites : uniquement via leur propre domaine (vhost dans /var/lib/vzone/nginx/domains/)"
