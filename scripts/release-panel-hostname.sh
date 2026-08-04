#!/usr/bin/env bash
# Retire un FQDN de VZONE_PANEL_HOSTNAMES pour qu'il serve un site client (pas le panel).
# Accès panel ensuite : https://<IP>/login
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

DOMAIN="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]' | sed 's/\.$//' | xargs)"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_DIR="${REPO_DIR:-/opt/vzone-src}"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
[[ -d "$REPO_DIR" ]] || REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -z "$DOMAIN" ]]; then
  echo "Usage: $0 <fqdn>"
  echo "Exemple: $0 vpanel.vzonecloud.co.uk"
  exit 2
fi

echo "=== release-panel-hostname: ${DOMAIN} ==="

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Fichier env introuvable: $ENV_FILE"
  exit 1
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

CURRENT="${VZONE_PANEL_HOSTNAMES:-}"
NEW_LIST=""
IFS=',' read -r -a arr <<< "${CURRENT}"
for h in "${arr[@]}"; do
  h="$(echo "$h" | xargs | tr '[:upper:]' '[:lower:]')"
  [[ -z "$h" || "$h" == "$DOMAIN" ]] && continue
  if [[ -z "$NEW_LIST" ]]; then
    NEW_LIST="$h"
  else
    NEW_LIST="${NEW_LIST},${h}"
  fi
done

if grep -q '^VZONE_PANEL_HOSTNAMES=' "$ENV_FILE"; then
  sed -i "s|^VZONE_PANEL_HOSTNAMES=.*|VZONE_PANEL_HOSTNAMES=${NEW_LIST}|" "$ENV_FILE"
else
  echo "VZONE_PANEL_HOSTNAMES=${NEW_LIST}" >> "$ENV_FILE"
fi

echo "[1] VZONE_PANEL_HOSTNAMES: '${CURRENT}' → '${NEW_LIST}' (vide = panel via IP seulement)"

# Garder le domaine dans ALLOWED_HOSTS (Django) même s'il n'est plus panel
if grep -q '^VZONE_ALLOWED_HOSTS=' "$ENV_FILE"; then
  ALLOWED="$(grep '^VZONE_ALLOWED_HOSTS=' "$ENV_FILE" | head -n1 | cut -d= -f2-)"
  case ",${ALLOWED}," in
    *",${DOMAIN},"*) ;;
    *)
      sed -i "s|^VZONE_ALLOWED_HOSTS=.*|VZONE_ALLOWED_HOSTS=${ALLOWED},${DOMAIN}|" "$ENV_FILE"
      echo "[1b] Ajouté ${DOMAIN} à VZONE_ALLOWED_HOSTS"
      ;;
  esac
fi

echo "[2] Régénération nginx panel (sans ${DOMAIN})"
bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf" \
  || bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${REPO_DIR}/deploy/nginx/vzone.conf"

echo "[3] Recharger API (nouvelle env PANEL_HOSTNAMES)"
systemctl restart vzone 2>/dev/null || systemctl restart vzone-api 2>/dev/null || true
systemctl restart daphne 2>/dev/null || true
sleep 2

echo "[4] Recréer le vhost site pour ${DOMAIN}"
MANAGE=""
for c in "${VZONE_ROOT}/backend/manage.py" "${REPO_DIR}/backend/manage.py"; do
  [[ -f "$c" ]] && MANAGE="$c" && break
done
if [[ -n "$MANAGE" ]]; then
  cd "$(dirname "$MANAGE")"
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-vzone.settings.production}"
  if [[ -x "${VZONE_ROOT}/.venv/bin/python" ]]; then
    PY="${VZONE_ROOT}/.venv/bin/python"
  elif [[ -x "${VZONE_ROOT}/venv/bin/python" ]]; then
    PY="${VZONE_ROOT}/venv/bin/python"
  else
    PY="python3"
  fi
  "$PY" manage.py shell <<PY || echo "[!] sync vhost Django a échoué — sync depuis le panel Domains"
from apps.domains.models import Domain
from apps.domains.vhosts import sync_domain_vhost, sync_all_domain_vhosts
name = "${DOMAIN}".lower()
qs = Domain.objects.filter(name__iexact=name)
if qs.exists():
    for d in qs:
        path = sync_domain_vhost(d)
        print(f"  synced {d.name} → {path}")
else:
    print(f"  Domaine {name} absent en base — créez-le dans Domains, puis sync.")
    sync_all_domain_vhosts()
    print("  sync_all_domain_vhosts OK")
PY
else
  echo "[!] manage.py introuvable — ouvrez Domains dans le panel et resync le vhost"
fi

nginx -t && systemctl reload nginx

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "[5] Tests"
echo "  panel via IP : $(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 -H "Host: ${HOST_IP}" "http://127.0.0.1/login" || echo fail)"
echo "  site ${DOMAIN} : $(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 -H "Host: ${DOMAIN}" "http://127.0.0.1/" || echo fail)"
echo
echo "=== Terminé ==="
echo "Panel : https://${HOST_IP}/login"
echo "Site  : https://${DOMAIN}/  (après DNS + éventuel SSL dans Domains)"
echo "Ne remettez PAS ${DOMAIN} comme hostname panel dans Server Setup."
