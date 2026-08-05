#!/usr/bin/env bash
# Installe l'agent root Cron Jobs (file-queue → /etc/cron.d/vzone-<user>).
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_USER="${VZONE_USER:-vzone}"
JOBS_DIR="${VZONE_CRON_JOBS_DIR:-/var/lib/vzone/cron/jobs}"

echo "[vzone] Installation agent Cron Jobs"

mkdir -p "$JOBS_DIR" /var/lib/vzone/cron/preview
chown -R "${VZONE_USER}:${VZONE_USER}" /var/lib/vzone/cron
chmod 770 "$JOBS_DIR"

# cronie / cron
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq cron 2>/dev/null || true
systemctl enable --now cron 2>/dev/null || systemctl enable --now crond 2>/dev/null || true

install -m 755 "${REPO_DIR}/scripts/vzone-cron-agent.sh" /usr/local/sbin/vzone-cron-agent
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-cron-job.service" /etc/systemd/system/vzone-cron-job.service
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-cron-job.path" /etc/systemd/system/vzone-cron-job.path

systemctl daemon-reload
systemctl enable --now vzone-cron-job.path
systemctl start vzone-cron-job.service 2>/dev/null || true

echo "[vzone] Agent Cron OK — jobs: ${JOBS_DIR}"
