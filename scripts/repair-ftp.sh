#!/usr/bin/env bash
# Réparation / (ré)installation FTP Pure-FTPd + ExtAuth V-zone
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[vzone] Diagnostic FTP avant réparation"
echo "--- units ---"
systemctl list-unit-files 'pure-ftpd*' 'vzone-ftp*' 2>/dev/null | head -20 || true
echo "--- port 21 ---"
ss -lntp 2>/dev/null | grep -E ':21\s' || echo "(rien sur :21)"
echo "--- conf clés ---"
for f in Bind ExtAuth TLS CertFile UnixAuthentication PAMAuthentication; do
  p="/etc/pure-ftpd/conf/${f}"
  if [[ -f "$p" ]]; then
    echo "  ${f}=$(tr -d '\n' <"$p")"
  else
    echo "  ${f}=(absent)"
  fi
done
echo "--- auth links ---"
ls -la /etc/pure-ftpd/auth 2>/dev/null || echo "(pas de /etc/pure-ftpd/auth)"
echo "--- dernier journal pure-ftpd ---"
journalctl -xeu pure-ftpd.service -n 25 --no-pager 2>/dev/null || true
echo ""

exec bash "${SCRIPT_DIR}/install-ftp.sh"
