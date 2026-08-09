#!/usr/bin/env bash
# Remet le propriétaire d'un chemin d'app client sur l'UID jail (SQLite / media / logs).
# Usage: vzone-fix-app-perms <username> <path>
# path DOIT être sous ${HOME_ROOT}/${username}/
# Appelé via sudo -n depuis vzone-api uniquement.
set -euo pipefail

CLIENTS_GROUP="${VZONE_CLIENTS_GROUP:-vzone-clients}"
HOME_ROOT="${VZONE_HOME_ROOT:-/home}"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "root requis" >&2
  exit 1
fi

USERNAME="${1:-}"
TARGET="${2:-}"

if [[ -z "$USERNAME" || -z "$TARGET" ]]; then
  echo "Usage: vzone-fix-app-perms <username> <path>" >&2
  exit 2
fi

if [[ ! "$USERNAME" =~ ^[a-z][a-z0-9_-]{2,31}$ ]]; then
  echo "username invalide" >&2
  exit 2
fi

case "$USERNAME" in
  root|vzone|vmail|nobody|www|www-data|admin|mysql|postgres|ftp|mail)
    echo "username réservé" >&2
    exit 2
    ;;
esac

if ! id -u "$USERNAME" >/dev/null 2>&1; then
  echo "compte OS absent: ${USERNAME}" >&2
  exit 3
fi

# Normalise et confine sous le home client
TARGET_REAL="$(realpath -m "$TARGET")"
HOME_DIR="$(realpath -m "${HOME_ROOT}/${USERNAME}")"
case "$TARGET_REAL" in
  "${HOME_DIR}"|"${HOME_DIR}"/*) ;;
  *)
    echo "chemin hors home client: ${TARGET_REAL}" >&2
    exit 3
    ;;
esac

if [[ ! -e "$TARGET_REAL" ]]; then
  echo "chemin introuvable: ${TARGET_REAL}" >&2
  exit 4
fi

GROUP="$CLIENTS_GROUP"
if ! getent group "$GROUP" >/dev/null 2>&1; then
  GROUP="$USERNAME"
fi

# Propriétaire = compte jail (nécessaire après fichiers créés par user « vzone »)
chown -R "${USERNAME}:${GROUP}" "$TARGET_REAL"

# Dossiers d'écriture runtime
if [[ -d "$TARGET_REAL" ]]; then
  chmod u+rwx,g+rwx,o+rx "$TARGET_REAL" 2>/dev/null || chmod 775 "$TARGET_REAL" || true
  for sub in logs media var tmp staticfiles data db database databases; do
    if [[ -d "${TARGET_REAL}/${sub}" ]]; then
      chmod 775 "${TARGET_REAL}/${sub}" 2>/dev/null || true
      chown -R "${USERNAME}:${GROUP}" "${TARGET_REAL}/${sub}" 2>/dev/null || true
    fi
  done
  # SQLite : fichier + journal (+ dossier parent déjà traité)
  while IFS= read -r -d '' db; do
    chmod 664 "$db" 2>/dev/null || chmod 666 "$db" 2>/dev/null || true
    chown "${USERNAME}:${GROUP}" "$db" 2>/dev/null || true
    for sfx in -wal -shm -journal; do
      if [[ -e "${db}${sfx}" ]]; then
        chown "${USERNAME}:${GROUP}" "${db}${sfx}" 2>/dev/null || true
        chmod 664 "${db}${sfx}" 2>/dev/null || true
      fi
    done
  done < <(find "$TARGET_REAL" -maxdepth 2 -type f \( -name '*.sqlite3' -o -name '*.sqlite' -o -name '*.db' \) -print0 2>/dev/null)
fi

# ACL panel pour continuer à gérer les fichiers
if command -v setfacl >/dev/null 2>&1; then
  VZONE_USER="${VZONE_USER:-vzone}"
  setfacl -R -m "u:${VZONE_USER}:rwx" "$TARGET_REAL" 2>/dev/null || true
  setfacl -R -d -m "u:${VZONE_USER}:rwx" "$TARGET_REAL" 2>/dev/null || true
fi

# Logs / pid : le panel (vzone) doit pouvoir append (stdout gunicorn via FD)
# même après chown jail — sinon start → Permission denied sur access.log
if [[ -d "${TARGET_REAL}/logs" ]]; then
  chmod 775 "${TARGET_REAL}/logs" 2>/dev/null || true
  find "${TARGET_REAL}/logs" -maxdepth 1 -type f \( -name '*.log' -o -name 'app.pid' \) \
    -exec chmod 666 {} \; 2>/dev/null || true
  if command -v setfacl >/dev/null 2>&1; then
    VZONE_USER="${VZONE_USER:-vzone}"
    find "${TARGET_REAL}/logs" -maxdepth 1 -type f \( -name '*.log' -o -name 'app.pid' \) \
      -exec setfacl -m "u:${VZONE_USER}:rw" {} \; 2>/dev/null || true
    setfacl -m "u:${VZONE_USER}:rwx" "${TARGET_REAL}/logs" 2>/dev/null || true
  fi
elif [[ -f "$TARGET_REAL" && "$TARGET_REAL" == *.log ]]; then
  chmod 666 "$TARGET_REAL" 2>/dev/null || true
  if command -v setfacl >/dev/null 2>&1; then
    setfacl -m "u:${VZONE_USER:-vzone}:rw" "$TARGET_REAL" 2>/dev/null || true
  fi
fi

echo "OK ${USERNAME} → ${TARGET_REAL}"
