#!/usr/bin/env bash
# Terminal WHM admin — shell root UNIQUEMENT avec ticket one-shot (anti RCE→root).
# Usage:
#   vzone-rootterm --check
#   vzone-rootterm --ticket /var/lib/vzone/terminal/tickets/<id>
set -euo pipefail

TICKETS_DIR="${VZONE_ROOTTERM_TICKETS:-/var/lib/vzone/terminal/tickets}"
MAX_AGE_SEC="${VZONE_ROOTTERM_TICKET_TTL:-90}"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "root requis (sudoers vzone-panel)" >&2
  exit 1
fi

if [[ "${1:-}" == "--check" ]]; then
  exit 0
fi

if [[ "${1:-}" != "--ticket" || -z "${2:-}" ]]; then
  echo "Usage: vzone-rootterm --ticket <path>" >&2
  echo "Ticket one-shot requis (émis par l'API après auth admin JWT)." >&2
  exit 2
fi

TICKET="$2"
# Ticket doit être sous TICKETS_DIR (pas de path traversal)
TICKET_REAL="$(realpath -m "$TICKET")"
case "$TICKET_REAL" in
  "${TICKETS_DIR}"/*) ;;
  *)
    echo "ticket path invalide" >&2
    exit 2
    ;;
esac

if [[ ! -f "$TICKET_REAL" ]]; then
  echo "ticket absent ou déjà consommé" >&2
  exit 3
fi

# Âge max
now="$(date +%s)"
mtime="$(stat -c %Y "$TICKET_REAL" 2>/dev/null || echo 0)"
age=$((now - mtime))
if [[ "$age" -gt "$MAX_AGE_SEC" || "$age" -lt 0 ]]; then
  rm -f "$TICKET_REAL" 2>/dev/null || true
  echo "ticket expiré" >&2
  exit 3
fi

# Contenu minimal (nonce)
size="$(stat -c %s "$TICKET_REAL" 2>/dev/null || echo 0)"
if [[ "$size" -lt 16 || "$size" -gt 512 ]]; then
  rm -f "$TICKET_REAL" 2>/dev/null || true
  echo "ticket invalide" >&2
  exit 3
fi

# Consommation atomique one-shot
rm -f "$TICKET_REAL" || {
  echo "ticket déjà consommé" >&2
  exit 3
}

logger -t vzone-rootterm "root shell opened (ticket consumed)"

export HOME=/root
export USER=root
export LOGNAME=root
export USERNAME=root
export SHELL=/bin/bash
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM="${TERM:-xterm-256color}"
unset SUDO_COMMAND SUDO_USER SUDO_UID SUDO_GID SUDO_PROMPT
cd /root || cd /

exec /bin/bash -l
