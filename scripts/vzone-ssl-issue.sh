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

# JSON compact pour le panel (chemins uniquement — les PEM sont lus par Django)
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
