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
TLS_COMBINED="/etc/ssl/private/vzone-pure-ftpd.pem"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi
DATA_ROOT="${VZONE_DATA_ROOT:-$DATA_ROOT}"

log() { echo "[vzone] $*"; }
warn() { echo "[vzone] AVERTISSEMENT — $*" >&2; }

log "Installation Pure-FTPd (auth V-zone)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq pure-ftpd openssl ca-certificates curl ssl-cert 2>/dev/null \
  || apt-get install -y -qq pure-ftpd openssl ca-certificates curl

# Binaire auth (Django direct — pas besoin d'HTTP)
install -m 755 "${REPO_DIR}/scripts/vzone-ftp-auth.py" "$AUTH_BIN"
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  sed -i "1s|^#!.*|#!${VZONE_ROOT}/backend/.venv/bin/python|" "$AUTH_BIN" || true
fi

mkdir -p "${DATA_ROOT}/ftp" /var/log/vzone /var/run
chown -R "${VZONE_USER}:${VZONE_USER}" "${DATA_ROOT}/ftp" 2>/dev/null || true
chmod 750 "${DATA_ROOT}/ftp" 2>/dev/null || true

# Secret auth — générer si absent
if [[ -f "$ENV_FILE" ]]; then
  if ! grep -qE '^VZONE_FTP_AUTH_SECRET=.+' "$ENV_FILE" 2>/dev/null; then
    SECRET="$(openssl rand -hex 24)"
    sed -i '/^VZONE_FTP_AUTH_SECRET=/d' "$ENV_FILE" 2>/dev/null || true
    echo "VZONE_FTP_AUTH_SECRET=${SECRET}" >>"$ENV_FILE"
    log "VZONE_FTP_AUTH_SECRET ajouté à ${ENV_FILE}"
  fi
fi

# --- pure-authd (systemd) ---
# NOTE: pure-authd Debian/Ubuntu n'a PAS d'option -l (log) — elle fait planter le daemon
# Options valides : -s socket, -r run, -p pidfile, -u uid, -g gid, -B daemonize
cat >"${UNIT_DIR}/vzone-ftp-authd.service" <<EOF
[Unit]
Description=V-zone Pure-FTPd ExtAuth daemon
After=network.target vzone-api.service
Wants=vzone-api.service
Before=pure-ftpd.service

[Service]
Type=simple
EnvironmentFile=-${ENV_FILE}
Environment=VZONE_ROOT=${VZONE_ROOT}
Environment=DJANGO_SETTINGS_MODULE=vzone.settings.production
ExecStartPre=/bin/rm -f ${AUTH_SOCK}
# Pas de -B : rester au premier plan (Type=simple). Pas de -l (inexistant sur Ubuntu).
ExecStart=/usr/sbin/pure-authd -s ${AUTH_SOCK} -r ${AUTH_BIN} -p /run/vzone-ftp-authd.pid
Restart=on-failure
RestartSec=2
UMask=0007
StandardOutput=append:/var/log/vzone/ftp-authd.log
StandardError=append:/var/log/vzone/ftp-authd.log

[Install]
WantedBy=multi-user.target
EOF

# Drop-in : Pure-FTPd démarre après ExtAuth (évite échec socket)
mkdir -p "${UNIT_DIR}/pure-ftpd.service.d"
cat >"${UNIT_DIR}/pure-ftpd.service.d/vzone.conf" <<EOF
[Unit]
After=vzone-ftp-authd.service network-online.target
Wants=vzone-ftp-authd.service
EOF

# --- Conf Pure-FTPd (Debian style / pure-ftpd-wrapper) ---
mkdir -p /etc/pure-ftpd/conf /etc/pure-ftpd/auth

# ExtAuth uniquement
echo "${AUTH_SOCK}" >/etc/pure-ftpd/conf/ExtAuth
rm -f /etc/pure-ftpd/auth/*
ln -sfn ../conf/ExtAuth /etc/pure-ftpd/auth/50ext
# Retirer les méthodes Debian par défaut qui cassent le démarrage / auth
rm -f /etc/pure-ftpd/auth/70unix /etc/pure-ftpd/auth/65unix \
  /etc/pure-ftpd/auth/60pam /etc/pure-ftpd/auth/PureDB \
  /etc/pure-ftpd/conf/UnixAuthentication /etc/pure-ftpd/conf/PAMAuthentication \
  /etc/pure-ftpd/conf/MySQLConfigFile /etc/pure-ftpd/conf/LDAPConfigFile 2>/dev/null || true
echo "no" >/etc/pure-ftpd/conf/UnixAuthentication
echo "no" >/etc/pure-ftpd/conf/PAMAuthentication

# Options panneau
echo "yes" >/etc/pure-ftpd/conf/ChrootEveryone
echo "yes" >/etc/pure-ftpd/conf/NoAnonymous
echo "yes" >/etc/pure-ftpd/conf/DontResolve
echo "yes" >/etc/pure-ftpd/conf/VerboseLog
echo "yes" >/etc/pure-ftpd/conf/Daemonize
# Format Debian : IP,port (un simple « 21 » fait souvent échouer le wrapper)
echo "0.0.0.0,21" >/etc/pure-ftpd/conf/Bind
echo "30000 30100" >/etc/pure-ftpd/conf/PassivePortRange
echo "yes" >/etc/pure-ftpd/conf/NoChmod
echo "100" >/etc/pure-ftpd/conf/MinUID
echo "15" >/etc/pure-ftpd/conf/MaxClientsNumber
echo "no" >/etc/pure-ftpd/conf/DisplayDotFiles 2>/dev/null || true

# TLS : Pure-FTPd exige un PEM cert+clé combinés — le snakeoil séparé fait crasher le start
rm -f /etc/pure-ftpd/conf/TLS /etc/pure-ftpd/conf/CertFile /etc/pure-ftpd/conf/TLSCipherSuite 2>/dev/null || true
if [[ -f /etc/ssl/certs/ssl-cert-snakeoil.pem && -f /etc/ssl/private/ssl-cert-snakeoil.key ]]; then
  cat /etc/ssl/certs/ssl-cert-snakeoil.pem /etc/ssl/private/ssl-cert-snakeoil.key >"${TLS_COMBINED}"
  chmod 640 "${TLS_COMBINED}"
  chown root:root "${TLS_COMBINED}" 2>/dev/null || true
  echo "1" >/etc/pure-ftpd/conf/TLS
  echo "${TLS_COMBINED}" >/etc/pure-ftpd/conf/CertFile
  log "TLS FTP activé (${TLS_COMBINED})"
else
  log "TLS FTP désactivé (pas de snakeoil) — FTP clair sur le port 21"
fi

# Port 21 déjà pris ?
if ss -lntp 2>/dev/null | grep -qE ':21\s' || netstat -lntp 2>/dev/null | grep -qE ':21\s'; then
  warn "Le port 21 est déjà utilisé — arrêt des conflits éventuels"
  systemctl stop vsftpd proftpd pure-ftpd-mysql 2>/dev/null || true
fi

# Firewall
if command -v ufw >/dev/null 2>&1; then
  ufw allow 21/tcp >/dev/null 2>&1 || true
  ufw allow 30000:30100/tcp >/dev/null 2>&1 || true
fi
if command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-service=ftp 2>/dev/null || firewall-cmd --permanent --add-port=21/tcp || true
  firewall-cmd --permanent --add-port=30000-30100/tcp 2>/dev/null || true
  firewall-cmd --reload 2>/dev/null || true
fi

touch /var/log/vzone/ftp-authd.log
chmod 664 /var/log/vzone/ftp-authd.log 2>/dev/null || true

systemctl daemon-reload
systemctl enable vzone-ftp-authd.service
systemctl stop vzone-ftp-authd.service 2>/dev/null || true
systemctl start vzone-ftp-authd.service || true

# Attendre que le socket ExtAuth existe (requis par pure-ftpd-wrapper)
SOCK_OK=0
for _ in $(seq 1 20); do
  if [[ -S "${AUTH_SOCK}" ]] && systemctl is-active --quiet vzone-ftp-authd.service; then
    SOCK_OK=1
    break
  fi
  sleep 0.25
done

if [[ "${SOCK_OK}" -ne 1 ]]; then
  warn "Socket ExtAuth absent (${AUTH_SOCK}) — journal authd :"
  journalctl -u vzone-ftp-authd.service -n 40 --no-pager || true
  # Test manuel sans -l
  warn "Test manuel pure-authd :"
  /usr/sbin/pure-authd -h 2>&1 | head -20 || true
  exit 1
fi
log "OK — vzone-ftp-authd actif (${AUTH_SOCK})"

systemctl enable pure-ftpd.service 2>/dev/null || systemctl enable pure-ftpd 2>/dev/null || true

set +e
systemctl restart pure-ftpd.service 2>/dev/null || systemctl restart pure-ftpd 2>/dev/null
RC=$?
set -e
sleep 1

if systemctl is-active --quiet pure-ftpd.service 2>/dev/null || systemctl is-active --quiet pure-ftpd 2>/dev/null; then
  log "OK — Pure-FTPd actif (port 21)"
else
  warn "Pure-FTPd non actif (restart rc=${RC})"
  if [[ -f /etc/pure-ftpd/conf/TLS ]]; then
    warn "Nouvelle tentative sans TLS…"
    rm -f /etc/pure-ftpd/conf/TLS /etc/pure-ftpd/conf/CertFile
    systemctl restart pure-ftpd.service 2>/dev/null || systemctl restart pure-ftpd 2>/dev/null || true
    sleep 1
  fi
  if systemctl is-active --quiet pure-ftpd.service 2>/dev/null || systemctl is-active --quiet pure-ftpd 2>/dev/null; then
    log "OK — Pure-FTPd actif (sans TLS)"
  else
    warn "Échec start — journal :"
    journalctl -xeu pure-ftpd.service -n 40 --no-pager || true
    if [[ -x /usr/sbin/pure-ftpd-wrapper ]]; then
      warn "Commande wrapper :"
      /usr/sbin/pure-ftpd-wrapper 2>&1 | head -5 || true
    fi
    exit 1
  fi
fi

log "FTP prêt. Comptes dans V-zone → FTP (login = username_compte, ex: user_web)."
