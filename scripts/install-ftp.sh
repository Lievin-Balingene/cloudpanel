#!/usr/bin/env bash
# V-zone — installe Pure-FTPd + auth ExtAuth (comptes panneau).
# Usage: sudo bash scripts/install-ftp.sh
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
VZONE_USER="${VZONE_USER:-vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
DATA_ROOT="${VZONE_DATA_ROOT:-/var/lib/vzone}"
AUTH_BIN="/usr/local/sbin/vzone-ftp-auth"
AUTH_SOCK="/var/run/vzone-ftp-authd.sock"
UNIT_DIR="/etc/systemd/system"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi
DATA_ROOT="${VZONE_DATA_ROOT:-$DATA_ROOT}"

echo "[vzone] Installation Pure-FTPd (auth V-zone)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq pure-ftpd openssl ca-certificates curl

# Binaire auth (Django direct — pas besoin d'HTTP)
install -m 755 "${REPO_DIR}/scripts/vzone-ftp-auth.py" "$AUTH_BIN"
# Shebang venv si dispo
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  sed -i "1s|^#!.*|#!${VZONE_ROOT}/backend/.venv/bin/python|" "$AUTH_BIN" || true
fi

mkdir -p "${DATA_ROOT}/ftp"
chown -R "${VZONE_USER}:${VZONE_USER}" "${DATA_ROOT}/ftp" 2>/dev/null || true
chmod 750 "${DATA_ROOT}/ftp" 2>/dev/null || true

# Secret auth (pour API HTTP optionnelle) — générer si absent
if [[ -f "$ENV_FILE" ]] && ! grep -q '^VZONE_FTP_AUTH_SECRET=' "$ENV_FILE" 2>/dev/null; then
  SECRET="$(openssl rand -hex 24)"
  echo "VZONE_FTP_AUTH_SECRET=${SECRET}" >>"$ENV_FILE"
  echo "[vzone] VZONE_FTP_AUTH_SECRET ajouté à ${ENV_FILE}"
elif [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
  if [[ -z "${VZONE_FTP_AUTH_SECRET:-}" ]]; then
    SECRET="$(openssl rand -hex 24)"
    sed -i '/^VZONE_FTP_AUTH_SECRET=/d' "$ENV_FILE"
    echo "VZONE_FTP_AUTH_SECRET=${SECRET}" >>"$ENV_FILE"
  fi
fi

# --- pure-authd (systemd) ---
cat >"${UNIT_DIR}/vzone-ftp-authd.service" <<EOF
[Unit]
Description=V-zone Pure-FTPd ExtAuth daemon
After=network.target vzone-api.service
Wants=vzone-api.service

[Service]
Type=simple
ExecStartPre=/bin/rm -f ${AUTH_SOCK}
ExecStart=/usr/sbin/pure-authd -s ${AUTH_SOCK} -r ${AUTH_BIN} -l /var/log/vzone/ftp-authd.log
Restart=on-failure
RestartSec=3
RuntimeDirectory=vzone-ftp
UMask=0007

[Install]
WantedBy=multi-user.target
EOF

# --- Conf Pure-FTPd (Debian style) ---
mkdir -p /etc/pure-ftpd/conf /etc/pure-ftpd/auth
# ExtAuth socket
echo "${AUTH_SOCK}" >/etc/pure-ftpd/conf/ExtAuth
# Auth order: ExtAuth only
rm -f /etc/pure-ftpd/auth/*
ln -sf ../conf/ExtAuth /etc/pure-ftpd/auth/50ext

# Options utiles panneau
echo "yes" >/etc/pure-ftpd/conf/ChrootEveryone
echo "yes" >/etc/pure-ftpd/conf/NoAnonymous
echo "yes" >/etc/pure-ftpd/conf/DontResolve
echo "yes" >/etc/pure-ftpd/conf/VerboseLog
echo "yes" >/etc/pure-ftpd/conf/Daemonize
echo "21" >/etc/pure-ftpd/conf/Bind
echo "30000 30100" >/etc/pure-ftpd/conf/PassivePortRange
echo "yes" >/etc/pure-ftpd/conf/NoChmod
echo "2" >/etc/pure-ftpd/conf/MinUID
# TLS optionnel si certificat présent
if [[ -f /etc/ssl/private/ssl-cert-snakeoil.key ]]; then
  echo "1" >/etc/pure-ftpd/conf/TLS
  echo "/etc/ssl/certs/ssl-cert-snakeoil.pem" >/etc/pure-ftpd/conf/CertFile
fi

# Passivewall
if command -v ufw >/dev/null 2>&1; then
  ufw allow 21/tcp || true
  ufw allow 30000:30100/tcp || true
fi
if command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-service=ftp 2>/dev/null || firewall-cmd --permanent --add-port=21/tcp || true
  firewall-cmd --permanent --add-port=30000-30100/tcp 2>/dev/null || true
  firewall-cmd --reload 2>/dev/null || true
fi

mkdir -p /var/log/vzone
touch /var/log/vzone/ftp-authd.log
chown "${VZONE_USER}:${VZONE_USER}" /var/log/vzone/ftp-authd.log 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now vzone-ftp-authd.service
# Pure-FTPd : certains paquets exposent pure-ftpd.service, d'autres pure-ftpd-mysql
systemctl enable pure-ftpd 2>/dev/null || systemctl enable pure-ftpd.service 2>/dev/null || true
systemctl restart pure-ftpd 2>/dev/null || systemctl restart pure-ftpd.service 2>/dev/null || true

sleep 1
if systemctl is-active --quiet vzone-ftp-authd.service; then
  echo "[vzone] OK — vzone-ftp-authd actif (${AUTH_SOCK})"
else
  echo "[vzone] AVERTISSEMENT — vzone-ftp-authd non actif" >&2
  systemctl status vzone-ftp-authd.service --no-pager -l || true
fi

if systemctl is-active --quiet pure-ftpd 2>/dev/null || systemctl is-active --quiet pure-ftpd.service 2>/dev/null; then
  echo "[vzone] OK — Pure-FTPd actif (port 21)"
else
  echo "[vzone] AVERTISSEMENT — Pure-FTPd non actif ; vérifiez: systemctl status pure-ftpd" >&2
fi

echo "[vzone] FTP prêt. Créez des comptes dans V-zone → FTP, login = username_compte (ex: user_web)."
