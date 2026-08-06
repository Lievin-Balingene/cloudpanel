#!/usr/bin/env bash
# Installe sudoers terminal + groupe vzone-clients (drop privileges web terminal)
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_DIR}/deploy/sudoers/vzone-terminal"
DEST="/etc/sudoers.d/vzone-terminal"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "Exécutez en root." >&2
  exit 1
fi

groupadd --system vzone-clients 2>/dev/null || true

install -m 440 "$SRC" "$DEST"
if ! visudo -cf "$DEST" >/dev/null 2>&1; then
  echo "[vzone] sudoers invalide — rollback" >&2
  rm -f "$DEST"
  exit 1
fi
echo "[vzone] sudoers terminal OK → $DEST (groupe vzone-clients)"
