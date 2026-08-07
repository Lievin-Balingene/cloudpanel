#!/usr/bin/env bash
# Installe l'agent reload Nginx (root) — requis pour appliquer les vhosts domaines.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "Exécutez en root." >&2
  exit 1
fi

mkdir -p /var/lib/vzone/nginx
chmod 775 /var/lib/vzone/nginx 2>/dev/null || true
chown vzone:www-data /var/lib/vzone/nginx 2>/dev/null || true

install -m 755 "${REPO_DIR}/scripts/vzone-nginx-reload.sh" /usr/local/sbin/vzone-nginx-reload
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-nginx-reload.service" /etc/systemd/system/vzone-nginx-reload.service
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-nginx-reload.path" /etc/systemd/system/vzone-nginx-reload.path
systemctl daemon-reload
systemctl enable vzone-nginx-reload.path 2>/dev/null || true
systemctl start vzone-nginx-reload.path 2>/dev/null || true
echo "[vzone] Agent nginx reload OK (vzone-nginx-reload.path)"
