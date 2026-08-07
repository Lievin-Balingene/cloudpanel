#!/usr/bin/env bash
# Installe vzone-mkhome + sudoers (création /home/<user> depuis le panel)
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "Exécutez en root." >&2
  exit 1
fi

VZONE_USER="${VZONE_USER:-vzone}"
install -m 755 "${REPO_DIR}/scripts/vzone-mkhome.sh" /usr/local/sbin/vzone-mkhome

# Remplace l'ancien fichier terminal-only s'il existe
rm -f /etc/sudoers.d/vzone-terminal
install -m 440 "${REPO_DIR}/deploy/sudoers/vzone-panel" /etc/sudoers.d/vzone-panel
if ! visudo -cf /etc/sudoers.d/vzone-panel >/dev/null 2>&1; then
  echo "[vzone] sudoers invalide — rollback" >&2
  rm -f /etc/sudoers.d/vzone-panel
  exit 1
fi

groupadd --system vzone-clients 2>/dev/null || true

# Droits sur /home pour créations suivantes (ACL ou groupe)
HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
mkdir -p "${HOME_ROOT}"
if command -v setfacl >/dev/null 2>&1; then
  setfacl -m "u:${VZONE_USER}:rwx" "${HOME_ROOT}" || true
  setfacl -d -m "u:${VZONE_USER}:rwx" "${HOME_ROOT}" || true
  echo "[vzone] ACL u:${VZONE_USER}:rwx sur ${HOME_ROOT}"
else
  chown "root:${VZONE_USER}" "${HOME_ROOT}" || true
  chmod 2775 "${HOME_ROOT}" || true
  echo "[vzone] ${HOME_ROOT} → root:${VZONE_USER} mode 2775"
fi

echo "[vzone] mkhome OK → /usr/local/sbin/vzone-mkhome + /etc/sudoers.d/vzone-panel"
