#!/usr/bin/env bash
# Réparation complète jour-0 / urgence : relance ensure + réparations safe.
# Usage: sudo bash scripts/repair-full-bootstrap.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "=== repair-full-bootstrap ==="
bash "${SCRIPT_DIR}/post-install-bootstrap.sh" --repair-only
echo "=== OK ==="
