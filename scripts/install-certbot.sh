#!/usr/bin/env bash
# Installe certbot + agent root (file queue) pour Let's Encrypt.
# Pas de sudo depuis l'API (NoNewPrivileges=true sur vzone-api).
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_USER="${VZONE_USER:-vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
ACME_ROOT="${VZONE_ACME_WEBROOT:-/var/lib/vzone/acme}"
SSL_ROOT="${VZONE_SSL_STORAGE:-/var/lib/vzone/ssl}"
JOBS_DIR="${SSL_ROOT}/jobs"

echo "[vzone] Installation certbot (Let's Encrypt)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq certbot

mkdir -p "$ACME_ROOT" "$SSL_ROOT" "$JOBS_DIR"
chown -R root:www-data "$ACME_ROOT"
chmod 755 "$ACME_ROOT"
mkdir -p "${ACME_ROOT}/.well-known/acme-challenge"
chmod -R a+rX "$ACME_ROOT"

chown -R "${VZONE_USER}:www-data" "$SSL_ROOT"
chmod 750 "$SSL_ROOT"
# Le panel (user vzone) dépose les jobs ; l'agent root les traite
chown "${VZONE_USER}:${VZONE_USER}" "$JOBS_DIR"
chmod 770 "$JOBS_DIR"

install -m 755 "${REPO_DIR}/scripts/vzone-ssl-issue.sh" /usr/local/sbin/vzone-ssl-issue
install -m 755 "${REPO_DIR}/scripts/vzone-ssl-agent.sh" /usr/local/sbin/vzone-ssl-agent

install -m 644 "${REPO_DIR}/deploy/systemd/vzone-ssl-job.service" /etc/systemd/system/vzone-ssl-job.service
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-ssl-job.path" /etc/systemd/system/vzone-ssl-job.path
systemctl daemon-reload
systemctl enable --now vzone-ssl-job.path
# Retirer l'ancien sudoers si présent (plus nécessaire)
rm -f /etc/sudoers.d/vzone-ssl 2>/dev/null || true

if [[ -f "$ENV_FILE" ]]; then
  grep -q '^VZONE_SSL_BACKEND=' "$ENV_FILE" || echo "VZONE_SSL_BACKEND=certbot" >> "$ENV_FILE"
  sed -i 's|^VZONE_SSL_BACKEND=.*|VZONE_SSL_BACKEND=certbot|' "$ENV_FILE"
  grep -q '^VZONE_ACME_WEBROOT=' "$ENV_FILE" || echo "VZONE_ACME_WEBROOT=${ACME_ROOT}" >> "$ENV_FILE"
  sed -i "s|^VZONE_ACME_WEBROOT=.*|VZONE_ACME_WEBROOT=${ACME_ROOT}|" "$ENV_FILE"
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

echo "[vzone] Agent SSL root: /usr/local/sbin/vzone-ssl-agent (path unit vzone-ssl-job.path)"
systemctl is-enabled vzone-ssl-job.path || true
