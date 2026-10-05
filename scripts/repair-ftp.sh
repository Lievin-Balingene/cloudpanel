#!/usr/bin/env bash
# Réparation / (ré)installation FTP Pure-FTPd + ExtAuth V-zone
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "${SCRIPT_DIR}/install-ftp.sh"
