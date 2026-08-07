#!/usr/bin/env bash
# Terminal client jailé (style jailshell) — UNIQUEMENT via sudo root depuis vzone-api.
# Usage:
#   vzone-jailterm <username>           # shell interactif PTY
#   vzone-jailterm --check <username>   # smoke-test (exit 0 si autorisé)
#
# Confinement: bubblewrap (UID/GID client, home seul en RW, pas de root, pas de /home voisins).
set -euo pipefail

CLIENTS_GROUP="${VZONE_CLIENTS_GROUP:-vzone-clients}"
HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
MODE="shell"
USERNAME=""

usage() {
  echo "Usage: vzone-jailterm [--check] <username>" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE="check"; shift ;;
    -h|--help) usage ;;
    *)
      if [[ -n "$USERNAME" ]]; then usage; fi
      USERNAME="$1"
      shift
      ;;
  esac
done

[[ -n "$USERNAME" ]] || usage

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "root requis (sudoers vzone-panel)" >&2
  exit 1
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

# Doit appartenir au groupe clients (anti-escalade vers comptes système)
if ! id -nG "$USERNAME" 2>/dev/null | tr ' ' '\n' | grep -qx "${CLIENTS_GROUP}"; then
  echo "${USERNAME} hors groupe ${CLIENTS_GROUP}" >&2
  exit 3
fi

HOME_DIR="$(getent passwd "$USERNAME" | cut -d: -f6)"
HOME_DIR="$(realpath -m "${HOME_DIR:-${HOME_ROOT}/${USERNAME}}")"
case "$HOME_DIR" in
  "${HOME_ROOT}"/"${USERNAME}") ;;
  *)
    echo "home hors ${HOME_ROOT}: ${HOME_DIR}" >&2
    exit 3
    ;;
esac

if [[ ! -d "$HOME_DIR" ]]; then
  echo "home absent: ${HOME_DIR}" >&2
  exit 3
fi

UID_NUM="$(id -u "$USERNAME")"
GID_NUM="$(id -g "$USERNAME")"

if [[ "$MODE" == "check" ]]; then
  if command -v bwrap >/dev/null 2>&1; then
    exit 0
  fi
  # Fallback sans bwrap toujours possible (restreint)
  exit 0
fi

# Environnement minimal — jamais d'escalade
export HOME="$HOME_DIR"
export USER="$USERNAME"
export LOGNAME="$USERNAME"
export USERNAME
export SHELL="/bin/bash"
export PATH="/usr/local/bin:/usr/bin:/bin"
export TERM="${TERM:-xterm-256color}"
export LANG="${LANG:-C.UTF-8}"
unset SUDO_COMMAND SUDO_USER SUDO_UID SUDO_GID SUDO_PROMPT
unset LD_PRELOAD LD_LIBRARY_PATH LD_AUDIT
unset BASH_ENV ENV CDPATH

run_restricted_fallback() {
  echo "[vzone-jail] bubblewrap absent — shell restreint (installez: apt install bubblewrap)" >&2
  cd "$HOME_DIR" || exit 1
  # bash --restricted : pas de cd hors HOME, pas de PATH/redir redirects vers hors...
  # (moins fort que bwrap ; bwrap reste la cible prod)
  exec runuser -u "$USERNAME" -- /bin/bash --restricted --noprofile --norc -i
}

if ! command -v bwrap >/dev/null 2>&1; then
  run_restricted_fallback
fi

# Binds de base (usr-merge Debian/Ubuntu + classiques)
BWRAP_ARGS=(
  --die-with-parent
  --unshare-pid
  --unshare-ipc
  --unshare-uts
  --hostname "$USERNAME"
  --uid "$UID_NUM"
  --gid "$GID_NUM"
  --cap-drop ALL
  --clearenv
  --setenv HOME "$HOME_DIR"
  --setenv USER "$USERNAME"
  --setenv LOGNAME "$USERNAME"
  --setenv USERNAME "$USERNAME"
  --setenv SHELL /bin/bash
  --setenv PATH /usr/local/bin:/usr/bin:/bin
  --setenv TERM "${TERM:-xterm-256color}"
  --setenv LANG "${LANG:-C.UTF-8}"
  --setenv PS1 "${USERNAME}:\w\$ "
)

# Filesystem : racine vide sauf binds explicites (pas de /home voisins, pas de /root, pas de /etc/sudoers)
ro_bind() {
  local src="$1" dst="${2:-$1}"
  if [[ -e "$src" ]]; then
    BWRAP_ARGS+=(--ro-bind "$src" "$dst")
  fi
}

ro_bind /usr /usr
if [[ -d /bin && ! -L /bin ]]; then
  ro_bind /bin /bin
else
  BWRAP_ARGS+=(--symlink usr/bin /bin)
fi
if [[ -d /sbin && ! -L /sbin ]]; then
  ro_bind /sbin /sbin
else
  BWRAP_ARGS+=(--symlink usr/sbin /sbin)
fi
if [[ -d /lib && ! -L /lib ]]; then
  ro_bind /lib /lib
else
  BWRAP_ARGS+=(--symlink usr/lib /lib)
fi
if [[ -e /lib64 ]]; then
  if [[ -d /lib64 && ! -L /lib64 ]]; then
    ro_bind /lib64 /lib64
  else
    BWRAP_ARGS+=(--symlink usr/lib64 /lib64)
  fi
fi
ro_bind /lib32 /lib32

ro_bind /etc/passwd
ro_bind /etc/group
ro_bind /etc/nsswitch.conf
ro_bind /etc/hosts
ro_bind /etc/resolv.conf
ro_bind /etc/ssl
ro_bind /etc/pki
ro_bind /etc/alternatives
ro_bind /etc/localtime
ro_bind /etc/terminfo
ro_bind /usr/share/terminfo /usr/share/terminfo
ro_bind /etc/bash.bashrc
ro_bind /etc/profile.d

# Dev / proc / tmp isolés
BWRAP_ARGS+=(
  --dev /dev
  --proc /proc
  --tmpfs /tmp
  --tmpfs /var/tmp
  --dir /run
  --dir /var
  --bind "$HOME_DIR" "$HOME_DIR"
  --chdir "$HOME_DIR"
)

# Pas de --ro-bind /etc entier (sudoers, shadow, ssh keys host…)
# Pas de réseau unshare : curl/git utiles aux clients ; FS déjà jailé.

exec bwrap "${BWRAP_ARGS[@]}" /bin/bash --noprofile --norc -i
