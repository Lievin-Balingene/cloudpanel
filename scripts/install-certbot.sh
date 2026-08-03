#!/usr/bin/env bash
# Installe certbot + sudoers pour que l'utilisateur vzone puisse émettre des certificats.
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_USER="${VZONE_USER:-vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
ACME_ROOT="${VZONE_ACME_WEBROOT:-/var/lib/vzone/acme}"
SSL_ROOT="${VZONE_SSL_STORAGE:-/var/lib/vzone/ssl}"

echo "[vzone] Installation certbot (Let's Encrypt)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq certbot

mkdir -p "$ACME_ROOT" "$SSL_ROOT"
# nginx (www-data) lit les challenges ; certbot (root) écrit
chown -R root:www-data "$ACME_ROOT"
chmod 755 "$ACME_ROOT"
mkdir -p "${ACME_ROOT}/.well-known/acme-challenge"
chmod -R a+rX "$ACME_ROOT"

chown -R "${VZONE_USER}:www-data" "$SSL_ROOT"
chmod 750 "$SSL_ROOT"

install -m 755 "${REPO_DIR}/scripts/vzone-ssl-issue.sh" /usr/local/sbin/vzone-ssl-issue

# Sudo sans mot de passe pour l'émission SSL uniquement
cat > /etc/sudoers.d/vzone-ssl <<EOF
# V-zone Panel — Let's Encrypt (certbot via wrapper)
Defaults:${VZONE_USER} !requiretty
${VZONE_USER} ALL=(root) NOPASSWD: /usr/local/sbin/vzone-ssl-issue
EOF
chmod 440 /etc/sudoers.d/vzone-ssl
visudo -cf /etc/sudoers.d/vzone-ssl

if [[ -f "$ENV_FILE" ]]; then
  grep -q '^VZONE_SSL_BACKEND=' "$ENV_FILE" || echo "VZONE_SSL_BACKEND=certbot" >> "$ENV_FILE"
  sed -i 's|^VZONE_SSL_BACKEND=.*|VZONE_SSL_BACKEND=certbot|' "$ENV_FILE"
  grep -q '^VZONE_ACME_WEBROOT=' "$ENV_FILE" || echo "VZONE_ACME_WEBROOT=${ACME_ROOT}" >> "$ENV_FILE"
  sed -i "s|^VZONE_ACME_WEBROOT=.*|VZONE_ACME_WEBROOT=${ACME_ROOT}|" "$ENV_FILE"
  # Hostname panel courant (si connu)
  if [[ -n "${VZONE_PANEL_HOSTNAMES:-}" ]]; then
    grep -q '^VZONE_PANEL_HOSTNAMES=' "$ENV_FILE" || echo "VZONE_PANEL_HOSTNAMES=${VZONE_PANEL_HOSTNAMES}" >> "$ENV_FILE"
  elif ! grep -q '^VZONE_PANEL_HOSTNAMES=' "$ENV_FILE"; then
    echo "VZONE_PANEL_HOSTNAMES=vpanel.vzonecloud.co.uk" >> "$ENV_FILE"
  fi
fi

if command -v certbot >/dev/null 2>&1; then
  echo "[vzone] certbot OK: $(command -v certbot) ($(certbot --version 2>&1 | head -n1))"
else
  echo "[vzone] ERREUR: certbot non installé" >&2
  exit 1
fi

echo "[vzone] Wrapper /usr/local/sbin/vzone-ssl-issue + sudoers pour ${VZONE_USER}"
