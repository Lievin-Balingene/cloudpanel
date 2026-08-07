#!/usr/bin/env bash
# Compat : délègue à ensure-mkhome-sudoers.sh (sudoers unifié panel)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/ensure-mkhome-sudoers.sh"
