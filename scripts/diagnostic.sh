#!/usr/bin/env bash
# Diagnostic système pour le support V-zone
set -euo pipefail

echo "=== V-zone Diagnostic $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "--- OS ---"
uname -a
[[ -f /etc/os-release ]] && cat /etc/os-release
echo "--- Versions ---"
python3 --version 2>/dev/null || true
node --version 2>/dev/null || true
nginx -v 2>&1 || true
psql --version 2>/dev/null || true
redis-cli --version 2>/dev/null || true
echo "--- Services ---"
systemctl is-active vzone-api vzone-worker vzone-beat nginx postgresql redis-server redis 2>/dev/null || true
echo "--- Disque / Mémoire ---"
df -h /
free -h 2>/dev/null || true
echo "--- Ports ---"
ss -tulpn 2>/dev/null | head -n 40 || netstat -tulpn 2>/dev/null | head -n 40 || true
echo "--- Derniers logs API ---"
journalctl -u vzone-api -n 50 --no-pager 2>/dev/null || true
echo "=== Fin diagnostic ==="
