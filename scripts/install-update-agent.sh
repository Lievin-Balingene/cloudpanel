#!/usr/bin/env bash
# Installe l'agent root de mise à jour panel (WHM → git pull + update.sh).
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_USER="${VZONE_USER:-vzone}"
JOBS_DIR="/var/lib/vzone/update/jobs"

echo "[vzone] Installation agent mise à jour panel (WHM)"
mkdir -p "${JOBS_DIR}"
chown "${VZONE_USER}:${VZONE_USER}" /var/lib/vzone/update "${JOBS_DIR}"
chmod 770 /var/lib/vzone/update "${JOBS_DIR}"

install -m 755 "${REPO_DIR}/scripts/vzone-update-agent.sh" /usr/local/sbin/vzone-update-agent
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-update-job.service" /etc/systemd/system/vzone-update-job.service
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-update-job.path" /etc/systemd/system/vzone-update-job.path

systemctl daemon-reload
systemctl enable --now vzone-update-job.path
echo "[vzone] Agent update prêt: vzone-update-job.path"
