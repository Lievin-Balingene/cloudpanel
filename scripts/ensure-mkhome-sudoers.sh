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

# Répare les comptes déjà créés hors groupe (sinon terminal sudo refuse)
repaired=0
for home_dir in "${HOME_ROOT}"/*; do
  [[ -d "$home_dir" ]] || continue
  u="$(basename "$home_dir")"
  [[ "$u" =~ ^[a-z][a-z0-9_-]{2,31}$ ]] || continue
  case "$u" in
    root|vzone|vmail|nobody|www|www-data|admin|mysql|postgres|ftp|mail) continue ;;
  esac
  if id -u "$u" >/dev/null 2>&1; then
    if ! id -nG "$u" 2>/dev/null | tr ' ' '\n' | grep -qx vzone-clients; then
      usermod -aG vzone-clients "$u" 2>/dev/null && repaired=$((repaired + 1)) || true
    fi
  fi
done
echo "[vzone] comptes ajoutés à vzone-clients: ${repaired}"

# Smoke-test sudoers (utilisateur panel → true en tant que membre du groupe)
if id -u "${VZONE_USER}" >/dev/null 2>&1; then
  sample="$(getent group vzone-clients | awk -F: '{print $4}' | tr ',' '\n' | head -n1)"
  if [[ -z "$sample" ]]; then
    # Aucun membre nommé : prendre un user dont le GID primaire = vzone-clients
    gid="$(getent group vzone-clients | cut -d: -f3 || true)"
    if [[ -n "$gid" ]]; then
      sample="$(getent passwd | awk -F: -v g="$gid" '$4==g {print $1; exit}')"
    fi
  fi
  if [[ -n "$sample" ]]; then
    if sudo -n -u "${VZONE_USER}" -- sudo -n -u "$sample" -- /bin/true 2>/dev/null; then
      echo "[vzone] smoke-test terminal sudo OK (${VZONE_USER} → ${sample})"
    else
      # Test direct en tant que root simulant le check panel
      if runuser -u "${VZONE_USER}" -- sudo -n -u "$sample" -- /bin/true 2>/dev/null \
        || su -s /bin/bash "${VZONE_USER}" -c "sudo -n -u ${sample} -- /bin/true" 2>/dev/null; then
        echo "[vzone] smoke-test terminal sudo OK (${VZONE_USER} → ${sample})"
      else
        echo "[vzone] Avertissement: smoke-test sudo terminal échoué pour ${sample}" >&2
        echo "[vzone] Vérifiez: cat /etc/sudoers.d/vzone-panel && id ${sample}" >&2
      fi
    fi
  fi
fi

echo "[vzone] mkhome OK → /usr/local/sbin/vzone-mkhome + /etc/sudoers.d/vzone-panel"
