#!/usr/bin/env bash
# Remet le propriétaire d'un chemin d'app client sur l'UID jail (SQLite / media / logs).
# SQLite exige le FICHIER et le DOSSIER parent en écriture (journaux -wal/-shm).
# Usage: vzone-fix-app-perms <username> <path>
# path DOIT être sous ${HOME_ROOT}/${username}/
# Appelé via sudo -n depuis vzone-api uniquement.
set -euo pipefail

CLIENTS_GROUP="${VZONE_CLIENTS_GROUP:-vzone-clients}"
HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
VZONE_USER="${VZONE_USER:-vzone}"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "root requis" >&2
  exit 1
fi

USERNAME="${1:-}"
TARGET="${2:-}"
FORCE=0
if [[ "${3:-}" == "--force" || "${2:-}" == "--force" ]]; then
  # allow: fix-app-perms user path --force  OR misplaced --force
  FORCE=1
fi
if [[ "${TARGET}" == "--force" ]]; then
  echo "Usage: vzone-fix-app-perms <username> <path> [--force]" >&2
  exit 2
fi

if [[ -z "$USERNAME" || -z "$TARGET" ]]; then
  echo "Usage: vzone-fix-app-perms <username> <path> [--force]" >&2
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

# Retirer attributs immuables éventuels (chattr +i)
if command -v chattr >/dev/null 2>&1; then
  chattr -R -i -a "$TARGET_REAL" 2>/dev/null || true
fi

# Chaîne parents : /home/<user> … → dossier app (traversée + écriture owner)
_fix_chain() {
  local p="$1"
  local cur="$p"
  local chain=()
  while [[ -n "$cur" && "$cur" != "/" && "$cur" != "$HOME_ROOT" ]]; do
    chain+=("$cur")
    [[ "$cur" == "$HOME_DIR" ]] && break
    cur="$(dirname "$cur")"
  done
  # Home lui-même
  if [[ -d "$HOME_DIR" ]]; then
    chown "${USERNAME}:${GROUP}" "$HOME_DIR" 2>/dev/null || true
    chmod u+rwx,g+rx,o-rwx "$HOME_DIR" 2>/dev/null || chmod 750 "$HOME_DIR" || true
  fi
  local d
  for d in "${chain[@]}"; do
    [[ -e "$d" ]] || continue
    chown "${USERNAME}:${GROUP}" "$d" 2>/dev/null || true
    if [[ -d "$d" ]]; then
      chmod u+rwx,g+rwx,o+rx "$d" 2>/dev/null || chmod 775 "$d" || true
    fi
  done
}
_fix_chain "$TARGET_REAL"

# Propriétaire récursif = compte jail
chown -R "${USERNAME}:${GROUP}" "$TARGET_REAL"

if [[ -d "$TARGET_REAL" ]]; then
  # Dossier app + sous-dossiers d'écriture runtime
  chmod u+rwx,g+rwx,o+rx "$TARGET_REAL" 2>/dev/null || chmod 775 "$TARGET_REAL" || true
  find "$TARGET_REAL" -type d -exec chmod u+rwx,g+rwx,o+rx {} \; 2>/dev/null || true

  for sub in logs media var tmp staticfiles data db database databases; do
    if [[ -d "${TARGET_REAL}/${sub}" ]]; then
      chown -R "${USERNAME}:${GROUP}" "${TARGET_REAL}/${sub}" 2>/dev/null || true
      chmod 775 "${TARGET_REAL}/${sub}" 2>/dev/null || true
    fi
  done

  # SQLite : fichier + journal (profondeur élargie — projets Django imbriqués)
  while IFS= read -r -d '' db; do
    chown "${USERNAME}:${GROUP}" "$db" 2>/dev/null || true
    chmod 664 "$db" 2>/dev/null || chmod 666 "$db" 2>/dev/null || true
    # Parent du .sqlite DOIT être writable (création -wal/-shm/-journal)
    parent="$(dirname "$db")"
    chown "${USERNAME}:${GROUP}" "$parent" 2>/dev/null || true
    chmod u+rwx,g+rwx,o+rx "$parent" 2>/dev/null || chmod 775 "$parent" || true
    for sfx in -wal -shm -journal; do
      if [[ -e "${db}${sfx}" ]]; then
        chown "${USERNAME}:${GROUP}" "${db}${sfx}" 2>/dev/null || true
        chmod 664 "${db}${sfx}" 2>/dev/null || true
      fi
    done
  done < <(find "$TARGET_REAL" -maxdepth 6 -type f \( -name '*.sqlite3' -o -name '*.sqlite' -o -name '*.db' \) -print0 2>/dev/null)
fi

if [[ -f "$TARGET_REAL" ]]; then
  chown "${USERNAME}:${GROUP}" "$TARGET_REAL" 2>/dev/null || true
  chmod 664 "$TARGET_REAL" 2>/dev/null || chmod 666 "$TARGET_REAL" 2>/dev/null || true
  parent="$(dirname "$TARGET_REAL")"
  chown "${USERNAME}:${GROUP}" "$parent" 2>/dev/null || true
  chmod u+rwx,g+rwx,o+rx "$parent" 2>/dev/null || true
fi

# ACL panel (gestion fichiers) + écriture jail explicite
if command -v setfacl >/dev/null 2>&1; then
  setfacl -R -m "u:${VZONE_USER}:rwx" "$TARGET_REAL" 2>/dev/null || true
  setfacl -R -d -m "u:${VZONE_USER}:rwx" "$TARGET_REAL" 2>/dev/null || true
  setfacl -R -m "u:${USERNAME}:rwx" "$TARGET_REAL" 2>/dev/null || true
  setfacl -R -d -m "u:${USERNAME}:rwx" "$TARGET_REAL" 2>/dev/null || true
  # Mask ACL : ne pas bloquer l'écriture owner/group
  setfacl -R -m "m::rwx" "$TARGET_REAL" 2>/dev/null || true
fi

# Logs / pid : panel (vzone) + jail doivent append
if [[ -d "${TARGET_REAL}/logs" ]]; then
  chmod 775 "${TARGET_REAL}/logs" 2>/dev/null || true
  find "${TARGET_REAL}/logs" -maxdepth 1 -type f \( -name '*.log' -o -name 'app.pid' \) \
    -exec chmod 666 {} \; 2>/dev/null || true
  if command -v setfacl >/dev/null 2>&1; then
    find "${TARGET_REAL}/logs" -maxdepth 1 -type f \( -name '*.log' -o -name 'app.pid' \) \
      -exec setfacl -m "u:${VZONE_USER}:rw" {} \; 2>/dev/null || true
    setfacl -m "u:${VZONE_USER}:rwx" "${TARGET_REAL}/logs" 2>/dev/null || true
  fi
elif [[ -f "$TARGET_REAL" && "$TARGET_REAL" == *.log ]]; then
  chmod 666 "$TARGET_REAL" 2>/dev/null || true
  if command -v setfacl >/dev/null 2>&1; then
    setfacl -m "u:${VZONE_USER}:rw" "$TARGET_REAL" 2>/dev/null || true
  fi
fi

# Vérification réelle : le jail peut écrire dans le dossier (et le sqlite si présent)
_VERIFY_DIR="$TARGET_REAL"
[[ -f "$TARGET_REAL" ]] && _VERIFY_DIR="$(dirname "$TARGET_REAL")"

_apply_force_world() {
  echo "FORCE: chmod permissif sur ${_VERIFY_DIR}" >&2
  chmod -R a+rwX "${_VERIFY_DIR}" 2>/dev/null || true
  find "${_VERIFY_DIR}" -type d -exec chmod 777 {} \; 2>/dev/null || true
  find "${_VERIFY_DIR}" -maxdepth 4 -type f \( -name '*.sqlite3' -o -name '*.sqlite' -o -name '*.db' -o -name '*-wal' -o -name '*-shm' -o -name '*-journal' \) \
    -exec chmod 666 {} \; 2>/dev/null || true
  chown -R "${USERNAME}:${GROUP}" "${_VERIFY_DIR}" 2>/dev/null || true
}

if [[ "$FORCE" -eq 1 ]]; then
  _apply_force_world
fi

_PROBE="${_VERIFY_DIR}/.vzone_write_probe_$$"
if command -v runuser >/dev/null 2>&1; then
  if ! runuser -u "$USERNAME" -- /bin/bash -c "touch $(printf '%q' "$_PROBE") && rm -f $(printf '%q' "$_PROBE")"; then
    echo "Probe écriture dossier échoué — tentative FORCE" >&2
    _apply_force_world
    if ! runuser -u "$USERNAME" -- /bin/bash -c "touch $(printf '%q' "$_PROBE") && rm -f $(printf '%q' "$_PROBE")"; then
      echo "ÉCHEC: ${USERNAME} ne peut pas écrire dans ${_VERIFY_DIR}" >&2
      ls -lad "$_VERIFY_DIR" >&2 || true
      getfacl -p "$_VERIFY_DIR" 2>/dev/null | head -20 >&2 || true
      exit 5
    fi
  fi
  for cand in "${_VERIFY_DIR}/db.sqlite3" "${TARGET_REAL}"; do
    if [[ -f "$cand" && "$cand" == *.sqlite3 ]]; then
      if ! runuser -u "$USERNAME" -- /bin/bash -c "test -w $(printf '%q' "$cand")"; then
        echo "Probe sqlite échoué — tentative FORCE" >&2
        _apply_force_world
        if ! runuser -u "$USERNAME" -- /bin/bash -c "test -w $(printf '%q' "$cand")"; then
          echo "ÉCHEC: ${USERNAME} ne peut pas écrire ${cand}" >&2
          ls -la "$cand" >&2 || true
          exit 5
        fi
      fi
    fi
  done
fi

echo "OK ${USERNAME} → ${TARGET_REAL}"
