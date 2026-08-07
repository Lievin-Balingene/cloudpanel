#!/usr/bin/env bash
# Terminal WHM admin — shell root interactif (style cPanel / WHM Terminal).
# Appelé UNIQUEMENT via sudo depuis vzone-api après auth JWT rôle administrator.
# Usage:
#   vzone-rootterm           # bash login root
#   vzone-rootterm --check   # smoke-test
set -euo pipefail

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "root requis (sudoers vzone-panel)" >&2
  exit 1
fi

if [[ "${1:-}" == "--check" ]]; then
  exit 0
fi

export HOME=/root
export USER=root
export LOGNAME=root
export USERNAME=root
export SHELL=/bin/bash
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM="${TERM:-xterm-256color}"
unset SUDO_COMMAND SUDO_USER SUDO_UID SUDO_GID SUDO_PROMPT
cd /root || cd /

# Login shell root — accès complet machine (WHM)
exec /bin/bash -l
