#!/usr/bin/env bash
# Installe l'agent root hostname (file queue) pour WHM Basic Setup.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_USER="${VZONE_USER:-vzone}"
JOBS_DIR="/var/lib/vzone/hostname/jobs"

echo "[vzone] Installation agent hostname WHM"
mkdir -p "${JOBS_DIR}"
chown "${VZONE_USER}:${VZONE_USER}" /var/lib/vzone/hostname "${JOBS_DIR}"
chmod 770 "${JOBS_DIR}"

install -m 755 "${REPO_DIR}/scripts/vzone-hostname-set.sh" /usr/local/sbin/vzone-hostname-set
install -m 755 "${REPO_DIR}/scripts/vzone-hostname-agent.sh" /usr/local/sbin/vzone-hostname-agent
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-hostname-job.service" /etc/systemd/system/vzone-hostname-job.service
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-hostname-job.path" /etc/systemd/system/vzone-hostname-job.path

systemctl daemon-reload
systemctl enable --now vzone-hostname-job.path
echo "[vzone] Agent hostname prêt: vzone-hostname-job.path"
