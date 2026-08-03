#!/usr/bin/env bash
# Émet un certificat Let's Encrypt (webroot) et copie les PEM dans le stockage V-zone.
# Usage: vzone-ssl-issue <domain> <email> [extra-hostname ...]
# Sortie JSON sur stdout : {"cert":"...","fullchain":"...","privkey":"..."}
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }

DOMAIN="${1:-}"
EMAIL="${2:-}"
shift 2 || true

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  echo "Usage: vzone-ssl-issue <domain> <email> [extra-hostname ...]" >&2
  exit 2
fi

ACME_ROOT="${VZONE_ACME_WEBROOT:-/var/lib/vzone/acme}"
SSL_ROOT="${VZONE_SSL_STORAGE:-/var/lib/vzone/ssl}"
OUT="${SSL_ROOT}/${DOMAIN}"
CERT_NAME="${DOMAIN}"

mkdir -p "${ACME_ROOT}/.well-known/acme-challenge" "$OUT"
chmod -R a+rX "$ACME_ROOT"

DOMAINS_ARGS=(-d "$DOMAIN")
for extra in "$@"; do
  [[ -n "$extra" ]] || continue
  DOMAINS_ARGS+=(-d "$extra")
done

certbot certonly \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  --webroot \
  -w "$ACME_ROOT" \
  --cert-name "$CERT_NAME" \
  --keep-until-expiring \
  --preferred-challenges http \
  "${DOMAINS_ARGS[@]}" >&2

LIVE="/etc/letsencrypt/live/${CERT_NAME}"
[[ -f "${LIVE}/fullchain.pem" ]] || { echo "Certificat introuvable: ${LIVE}" >&2; exit 1; }

install -m 640 -o vzone -g www-data "${LIVE}/cert.pem" "${OUT}/cert.pem"
install -m 640 -o vzone -g www-data "${LIVE}/fullchain.pem" "${OUT}/fullchain.pem"
install -m 640 -o vzone -g www-data "${LIVE}/privkey.pem" "${OUT}/privkey.pem"
chmod 750 "$OUT" 2>/dev/null || true
chown vzone:www-data "$OUT"

# Appliquer HTTPS (vhosts déjà écrits par Django) — reload Nginx en root
# Si hostname panel : régénérer sites-enabled/vzone pour injecter le certificat
PANEL_HOSTS="${VZONE_PANEL_HOSTNAMES:-}"
if [[ -f /etc/vzone/vzone.env ]]; then
  # shellcheck disable=SC1091
  set -a; source /etc/vzone/vzone.env; set +a
  PANEL_HOSTS="${VZONE_PANEL_HOSTNAMES:-$PANEL_HOSTS}"
fi
IS_PANEL=0
DOMAIN_LC="$(printf '%s' "$DOMAIN" | tr '[:upper:]' '[:lower:]')"
for h in ${PANEL_HOSTS//,/ }; do
  [[ -n "$h" ]] || continue
  h_lc="$(printf '%s' "$h" | tr '[:upper:]' '[:lower:]')"
  if [[ "$h_lc" == "$DOMAIN_LC" ]]; then
    IS_PANEL=1
    break
  fi
done

# Annoncer le succès AVANT le reload Nginx : l'API peut finaliser même si
# la connexion proxy est brièvement coupée pendant le reload.
python3 - <<PY
import json
print(json.dumps({
    "domain": "${DOMAIN}",
    "cert_path": "${OUT}/cert.pem",
    "fullchain_path": "${OUT}/fullchain.pem",
    "privkey_path": "${OUT}/privkey.pem",
    "live_dir": "${LIVE}",
}))
PY

if [[ "$IS_PANEL" -eq 1 ]]; then
  # Ne pas restart nginx ni vzone-api pendant le POST /ssl/letsencrypt/
  export VZONE_SKIP_API_RESTART=1
  export VZONE_NGINX_RELOAD_ONLY=1
  for script in /opt/vzone-src/scripts/ensure-nginx.sh /opt/vzone/scripts/ensure-nginx.sh; do
    if [[ -f "$script" ]]; then
      bash "$script" || true
      break
    fi
  done
elif command -v nginx >/dev/null 2>&1; then
  if nginx -t 2>/dev/null; then
    systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
  else
    echo "[vzone-ssl-issue] nginx -t a échoué — certificats copiés mais HTTPS non rechargé" >&2
    nginx -t >&2 || true
  fi
fi
