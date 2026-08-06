#!/usr/bin/env bash
# Installe l'agent root des scripts de réparation WHM.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_USER="${VZONE_USER:-vzone}"
JOBS_DIR="/var/lib/vzone/repair/jobs"

echo "[vzone] Installation agent réparations WHM"
mkdir -p "${JOBS_DIR}"
chown "${VZONE_USER}:${VZONE_USER}" /var/lib/vzone/repair "${JOBS_DIR}" 2>/dev/null \
  || chown -R "${VZONE_USER}:${VZONE_USER}" /var/lib/vzone/repair
chmod 770 /var/lib/vzone/repair "${JOBS_DIR}"

install -m 755 "${REPO_DIR}/scripts/vzone-repair-agent.sh" /usr/local/sbin/vzone-repair-agent
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-repair-job.service" /etc/systemd/system/vzone-repair-job.service
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-repair-job.path" /etc/systemd/system/vzone-repair-job.path

systemctl daemon-reload
systemctl enable --now vzone-repair-job.path
echo "[vzone] Agent repair prêt: vzone-repair-job.path"
