#!/usr/bin/env bash
# Exécute une commande sous l'UID d'un compte vzone-clients (pas root, pas vzone).
# Usage: vzone-runas <username> -- <command> [args...]
# Appelé via sudo depuis vzone-api uniquement.
set -euo pipefail

CLIENTS_GROUP="${VZONE_CLIENTS_GROUP:-vzone-clients}"
HOME_ROOT="${VZONE_HOME_ROOT:-/home}"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "root requis" >&2
  exit 1
fi

USERNAME="${1:-}"
shift || true
if [[ "${1:-}" == "--" ]]; then
  shift
fi

if [[ -z "$USERNAME" || $# -lt 1 ]]; then
  echo "Usage: vzone-runas <username> -- <command> [args...]" >&2
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

if ! id -nG "$USERNAME" 2>/dev/null | tr ' ' '\n' | grep -qx "${CLIENTS_GROUP}"; then
  echo "${USERNAME} hors groupe ${CLIENTS_GROUP}" >&2
  exit 3
fi

HOME_DIR="$(getent passwd "$USERNAME" | cut -d: -f6)"
HOME_DIR="$(realpath -m "${HOME_DIR:-${HOME_ROOT}/${USERNAME}}")"
case "$HOME_DIR" in
  "${HOME_ROOT}"/"${USERNAME}") ;;
  *)
    echo "home hors ${HOME_ROOT}" >&2
    exit 3
    ;;
esac

# Résoudre runuser/su AVANT de restreindre PATH (runuser est souvent dans /usr/sbin).
_find_bin() {
  local name="$1" p
  p="$(command -v "$name" 2>/dev/null || true)"
  if [[ -n "$p" && -x "$p" ]]; then
    printf '%s\n' "$p"
    return 0
  fi
  for p in "/usr/sbin/${name}" "/sbin/${name}" "/usr/bin/${name}" "/bin/${name}"; do
    if [[ -x "$p" ]]; then
      printf '%s\n' "$p"
      return 0
    fi
  done
  return 1
}

RUNUSER_BIN="$(_find_bin runuser || true)"
SU_BIN="$(_find_bin su || true)"

# Environnement client : PATH restreint (pas de /sbin) — le helper root utilise un chemin absolu.
export HOME="$HOME_DIR"
export USER="$USERNAME"
export LOGNAME="$USERNAME"
export PATH="/usr/local/bin:/usr/bin:/bin"
unset SUDO_COMMAND SUDO_USER SUDO_UID SUDO_GID
unset LD_PRELOAD LD_LIBRARY_PATH

cd "$HOME_DIR" 2>/dev/null || cd /tmp

if [[ -n "$RUNUSER_BIN" ]]; then
  exec "$RUNUSER_BIN" -u "$USERNAME" -- "$@"
fi

if [[ -n "$SU_BIN" ]]; then
  # Fallback si util-linux/runuser absent : quoting bash sûr.
  _cmd=""
  for _a in "$@"; do
    _cmd+="$(printf '%q' "$_a") "
  done
  exec "$SU_BIN" -s /bin/bash "$USERNAME" -c "cd $(printf '%q' "$HOME_DIR") && exec ${_cmd}"
fi

echo "ni runuser ni su disponibles — installez util-linux (runuser)" >&2
exit 127
