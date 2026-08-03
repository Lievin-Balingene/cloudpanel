#!/usr/bin/env bash
# V-zone Panel — installateur production
# Usage: sudo bash scripts/install.sh [--non-interactive]
set -euo pipefail

VZONE_VERSION="$(tr -d '[:space:]' < "$(dirname "$0")/../VERSION" 2>/dev/null || echo "0.1.0")"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
VZONE_DATA="${VZONE_DATA:-/var/lib/vzone}"
VZONE_LOG="${VZONE_LOG:-/var/log/vzone}"
VZONE_USER="${VZONE_USER:-vzone}"
VZONE_DB_NAME="${VZONE_DB_NAME:-vzone}"
VZONE_DB_USER="${VZONE_DB_USER:-vzone}"
NON_INTERACTIVE=0

for arg in "$@"; do
  case "$arg" in
    --non-interactive) NON_INTERACTIVE=1 ;;
  esac
done

log()  { printf '\033[1;34m[vzone]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[erreur]\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
  [[ ${EUID:-0} -eq 0 ]] || fail "Exécutez ce script en root (sudo)."
}

detect_distro() {
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    DISTRO_ID="${ID:-unknown}"
    DISTRO_VERSION="${VERSION_ID:-}"
    DISTRO_FAMILY="unknown"
    case "$DISTRO_ID" in
      ubuntu|debian) DISTRO_FAMILY="debian" ;;
      almalinux|rocky|rhel|centos) DISTRO_FAMILY="rhel" ;;
    esac
  else
    fail "Impossible de détecter la distribution (/etc/os-release manquant)."
  fi
  log "Distribution détectée: ${DISTRO_ID} ${DISTRO_VERSION} (famille ${DISTRO_FAMILY})"
  [[ "$DISTRO_FAMILY" != "unknown" ]] || fail "Distribution non supportée: ${DISTRO_ID}"
}

install_packages_debian() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    curl ca-certificates gnupg lsb-release software-properties-common \
    build-essential git python3 python3-venv python3-dev python3-pip \
    postgresql postgresql-contrib redis-server nginx \
    libpq-dev libffi-dev libssl-dev pkg-config \
    ufw fail2ban
  # Node.js 20 LTS
  if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
  fi
  # Docker
  if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
  fi
}

install_packages_rhel() {
  dnf -y install epel-release || true
  dnf -y install \
    curl ca-certificates git gcc gcc-c++ make \
    python3 python3-devel python3-pip \
    postgresql-server postgresql-contrib redis nginx \
    libpq-devel openssl-devel libffi-devel \
    firewalld fail2ban
  if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
    dnf -y install nodejs
  fi
  if ! command -v docker >/dev/null 2>&1; then
    dnf -y install docker || curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
  fi
  postgresql-setup --initdb 2>/dev/null || true
  systemctl enable --now postgresql redis nginx
}

create_system_user() {
  if ! id "$VZONE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$VZONE_DATA" --shell /usr/sbin/nologin "$VZONE_USER"
    ok "Utilisateur système ${VZONE_USER} créé"
  fi
  mkdir -p "$VZONE_ROOT" "$VZONE_DATA" "$VZONE_LOG" /etc/vzone
  chown -R "$VZONE_USER":"$VZONE_USER" "$VZONE_DATA" "$VZONE_LOG"
}

setup_postgres() {
  VZONE_DB_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
  if [[ "$DISTRO_FAMILY" == "debian" ]]; then
    systemctl enable --now postgresql
    sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${VZONE_DB_USER}'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE USER ${VZONE_DB_USER} WITH PASSWORD '${VZONE_DB_PASSWORD}';"
    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${VZONE_DB_NAME}'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE DATABASE ${VZONE_DB_NAME} OWNER ${VZONE_DB_USER};"
  else
    systemctl enable --now postgresql
    sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${VZONE_DB_USER}'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE USER ${VZONE_DB_USER} WITH PASSWORD '${VZONE_DB_PASSWORD}';"
    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${VZONE_DB_NAME}'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE DATABASE ${VZONE_DB_NAME} OWNER ${VZONE_DB_USER};"
  fi
  ok "PostgreSQL configuré"
}

deploy_application() {
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
  rsync -a --delete \
    --exclude '.git' --exclude 'frontend/node_modules' --exclude 'backend/.venv' \
    --exclude '.data' --exclude '.logs' \
    "${REPO_DIR}/" "${VZONE_ROOT}/"

  SECRET_KEY="$(openssl rand -hex 48)"
  ADMIN_PASS="$(openssl rand -base64 18 | tr -d '/+=' | head -c 16)"
  cat > /etc/vzone/vzone.env <<EOF
VZONE_ENV=production
VZONE_SECRET_KEY=${SECRET_KEY}
VZONE_DEBUG=false
VZONE_ALLOWED_HOSTS=$(hostname -f),$(hostname -I | awk '{print $1}'),localhost,127.0.0.1
VZONE_DB_NAME=${VZONE_DB_NAME}
VZONE_DB_USER=${VZONE_DB_USER}
VZONE_DB_PASSWORD=${VZONE_DB_PASSWORD}
VZONE_DB_HOST=127.0.0.1
VZONE_DB_PORT=5432
VZONE_REDIS_URL=redis://127.0.0.1:6379/0
VZONE_CELERY_BROKER_URL=redis://127.0.0.1:6379/1
VZONE_CHANNELS_REDIS_URL=redis://127.0.0.1:6379/2
VZONE_DATA_ROOT=${VZONE_DATA}
VZONE_LOG_ROOT=${VZONE_LOG}
VZONE_HOME_ROOT=/home
VZONE_SECURE_SSL_REDIRECT=false
VZONE_VERSION=${VZONE_VERSION}
VZONE_ENABLED_MODULES=core,accounts,packages,dns,dashboard,domains,files,ftp,email,databases,python_apps,node_apps,php,git_deploy,docker_mgmt,backups,monitoring,firewall,security
EOF
  chmod 600 /etc/vzone/vzone.env
  ln -sfn /etc/vzone/vzone.env "${VZONE_ROOT}/.env"

  python3 -m venv "${VZONE_ROOT}/backend/.venv"
  # shellcheck disable=SC1091
  source "${VZONE_ROOT}/backend/.venv/bin/activate"
  pip install --upgrade pip wheel
  pip install -r "${VZONE_ROOT}/backend/requirements/prod.txt"
  cd "${VZONE_ROOT}/backend"
  set -a; source /etc/vzone/vzone.env; set +a
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
  ADMIN_EMAIL="admin@$(hostname -f 2>/dev/null || echo localhost)"
  python manage.py shell <<PY
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username="admin").exists():
    User.objects.create_superuser(
        email="${ADMIN_EMAIL}",
        username="admin",
        password="${ADMIN_PASS}",
    )
    u = User.objects.get(username="admin")
    u.must_change_password = True
    u.save(update_fields=["must_change_password"])
PY
  deactivate

  cd "${VZONE_ROOT}/frontend"
  npm ci || npm install
  npm run build

  install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-api.service" /etc/systemd/system/
  install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-worker.service" /etc/systemd/system/
  install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-beat.service" /etc/systemd/system/
  install -m 644 "${VZONE_ROOT}/deploy/nginx/vzone.conf" /etc/nginx/sites-available/vzone 2>/dev/null \
    || install -m 644 "${VZONE_ROOT}/deploy/nginx/vzone.conf" /etc/nginx/conf.d/vzone.conf
  if [[ -d /etc/nginx/sites-enabled ]]; then
    ln -sfn /etc/nginx/sites-available/vzone /etc/nginx/sites-enabled/vzone
    rm -f /etc/nginx/sites-enabled/default
  fi
  nginx -t
  systemctl daemon-reload
  systemctl enable --now redis-server 2>/dev/null || systemctl enable --now redis
  systemctl enable --now vzone-api vzone-worker vzone-beat nginx

  configure_firewall

  HOST_IP="$(hostname -I | awk '{print $1}')"
  cat > /etc/vzone/install-info.txt <<EOF
version=${VZONE_VERSION}
url=http://${HOST_IP}/
admin_user=admin
admin_email=${ADMIN_EMAIL}
admin_temp_password=${ADMIN_PASS}
installed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
  chmod 600 /etc/vzone/install-info.txt

  echo
  echo "============================================================"
  echo " Installation terminée."
  echo "============================================================"
  echo " URL d'accès          : http://${HOST_IP}/"
  echo " Utilisateur admin    : admin"
  echo " Mot de passe temp.   : ${ADMIN_PASS}"
  echo " Changer le mot de passe :"
  echo "   sudo -u ${VZONE_USER} ${VZONE_ROOT}/backend/.venv/bin/python \\"
  echo "     ${VZONE_ROOT}/backend/manage.py changepassword admin"
  echo " Version installée    : ${VZONE_VERSION}"
  echo " Services actifs      : vzone-api, vzone-worker, vzone-beat, nginx, postgresql, redis"
  echo "============================================================"
}

configure_firewall() {
  if command -v ufw >/dev/null 2>&1; then
    ufw allow OpenSSH || true
    ufw allow 80/tcp || true
    ufw allow 443/tcp || true
    ufw --force enable || true
  elif command -v firewall-cmd >/dev/null 2>&1; then
    systemctl enable --now firewalld
    firewall-cmd --permanent --add-service=ssh
    firewall-cmd --permanent --add-service=http
    firewall-cmd --permanent --add-service=https
    firewall-cmd --reload
  fi
  systemctl enable --now fail2ban 2>/dev/null || true
}

main() {
  require_root
  detect_distro
  log "Installation V-zone Panel ${VZONE_VERSION}"
  if [[ "$DISTRO_FAMILY" == "debian" ]]; then
    install_packages_debian
  else
    install_packages_rhel
  fi
  create_system_user
  setup_postgres
  systemctl enable --now redis-server 2>/dev/null || systemctl enable --now redis || true
  deploy_application
}

main "$@"
