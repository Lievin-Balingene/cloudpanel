#!/usr/bin/env bash
# Terminal client jailé (style jailshell) — UNIQUEMENT via sudo root depuis vzone-api.
# Usage:
#   vzone-jailterm <username>           # shell interactif PTY
#   vzone-jailterm --check <username>   # smoke-test (exit 0 si autorisé)
#
# Confinement: runuser (UID client) + bubblewrap setuid (home RW, pas de /root ni voisins).
# Évite --uid/--unshare-user (souvent bloqué quand user namespaces désactivés).
set -euo pipefail

CLIENTS_GROUP="${VZONE_CLIENTS_GROUP:-vzone-clients}"
HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
MODE="shell"
USERNAME=""
BWRAP_ARGS=()

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

build_bwrap_args() {
  BWRAP_ARGS=(
    --die-with-parent
    --unshare-pid
    --unshare-ipc
    --unshare-uts
    --hostname "$USERNAME"
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
}

bwrap_as_user() {
  build_bwrap_args
  runuser -u "$USERNAME" -- bwrap "${BWRAP_ARGS[@]}" "$@"
}

run_restricted_fallback() {
  echo "[vzone-jail] bubblewrap indisponible — bash restreint (apt install bubblewrap recommandé)" >&2
  exec runuser -u "$USERNAME" -- /bin/bash --restricted --noprofile --norc -i
}

if [[ "$MODE" == "check" ]]; then
  if command -v bwrap >/dev/null 2>&1 && command -v runuser >/dev/null 2>&1; then
    if bwrap_as_user /usr/bin/true 2>/dev/null; then
      exit 0
    fi
    echo "bwrap+runuser échoué — fallback bash --restricted disponible" >&2
  fi
  if command -v runuser >/dev/null 2>&1; then
    exit 0
  fi
  echo "runuser absent" >&2
  exit 4
fi

export TERM="${TERM:-xterm-256color}"
export LANG="${LANG:-C.UTF-8}"
unset SUDO_COMMAND SUDO_USER SUDO_UID SUDO_GID SUDO_PROMPT
unset LD_PRELOAD LD_LIBRARY_PATH LD_AUDIT
unset BASH_ENV ENV CDPATH

if command -v bwrap >/dev/null 2>&1 && command -v runuser >/dev/null 2>&1; then
  if bwrap_as_user /usr/bin/true 2>/dev/null; then
    build_bwrap_args
    exec runuser -u "$USERNAME" -- env \
      TERM="${TERM:-xterm-256color}" \
      LANG="${LANG:-C.UTF-8}" \
      bwrap "${BWRAP_ARGS[@]}" /bin/bash --noprofile --norc -i
  fi
fi

run_restricted_fallback
