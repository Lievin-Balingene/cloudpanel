#!/usr/bin/env bash
# Installe vzone-mkhome + vzone-jailterm + sudoers + bubblewrap
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "Exécutez en root." >&2
  exit 1
fi

VZONE_USER="${VZONE_USER:-vzone}"

# bubblewrap = confinement FS réel (jailshell)
if ! command -v bwrap >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq bubblewrap >/dev/null 2>&1 \
      || echo "[vzone] Avertissement: apt install bubblewrap a échoué" >&2
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q bubblewrap >/dev/null 2>&1 \
      || echo "[vzone] Avertissement: dnf install bubblewrap a échoué" >&2
  elif command -v yum >/dev/null 2>&1; then
    yum install -y -q bubblewrap >/dev/null 2>&1 \
      || echo "[vzone] Avertissement: yum install bubblewrap a échoué" >&2
  fi
fi
if command -v bwrap >/dev/null 2>&1; then
  echo "[vzone] bubblewrap OK ($(command -v bwrap))"
else
  echo "[vzone] Avertissement: bubblewrap absent — fallback bash --restricted" >&2
fi

install -m 755 "${REPO_DIR}/scripts/vzone-mkhome.sh" /usr/local/sbin/vzone-mkhome
install -m 755 "${REPO_DIR}/scripts/vzone-jailterm.sh" /usr/local/sbin/vzone-jailterm
install -m 755 "${REPO_DIR}/scripts/vzone-rootterm.sh" /usr/local/sbin/vzone-rootterm

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

# Répare membership + shell nologin + lock password (pas de login SSH/password)
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
    # Pas de shell login OS — terminal uniquement via vzone-jailterm
    usermod -s /usr/sbin/nologin "$u" 2>/dev/null \
      || usermod -s /sbin/nologin "$u" 2>/dev/null \
      || true
    passwd -l "$u" >/dev/null 2>&1 || true
    # Retirer tout sudoers client éventuel
    rm -f "/etc/sudoers.d/${u}" "/etc/sudoers.d/90-${u}" 2>/dev/null || true
  fi
done
echo "[vzone] comptes ajoutés à vzone-clients: ${repaired}"

# Smoke-test jailterm
if id -u "${VZONE_USER}" >/dev/null 2>&1; then
  sample=""
  for home_dir in "${HOME_ROOT}"/*; do
    [[ -d "$home_dir" ]] || continue
    u="$(basename "$home_dir")"
    if id -u "$u" >/dev/null 2>&1 && id -nG "$u" 2>/dev/null | tr ' ' '\n' | grep -qx vzone-clients; then
      sample="$u"
      break
    fi
  done
  if [[ -n "$sample" ]]; then
    if runuser -u "${VZONE_USER}" -- sudo -n /usr/local/sbin/vzone-jailterm --check "$sample" 2>/dev/null \
      || su -s /bin/bash "${VZONE_USER}" -c "sudo -n /usr/local/sbin/vzone-jailterm --check ${sample}" 2>/dev/null; then
      echo "[vzone] smoke-test jailterm OK (${VZONE_USER} → ${sample})"
    else
      echo "[vzone] Avertissement: smoke-test jailterm échoué pour ${sample}" >&2
      echo "[vzone] Vérifiez: cat /etc/sudoers.d/vzone-panel && NoNewPrivileges=false sur vzone-api" >&2
    fi
  fi
  if runuser -u "${VZONE_USER}" -- sudo -n /usr/local/sbin/vzone-rootterm --check 2>/dev/null \
    || su -s /bin/bash "${VZONE_USER}" -c "sudo -n /usr/local/sbin/vzone-rootterm --check" 2>/dev/null; then
    echo "[vzone] smoke-test rootterm OK (terminal WHM admin)"
  else
    echo "[vzone] Avertissement: smoke-test rootterm échoué" >&2
  fi
fi

echo "[vzone] jail OK → mkhome + jailterm + rootterm + /etc/sudoers.d/vzone-panel"
