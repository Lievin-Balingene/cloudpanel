#!/usr/bin/env bash
# Installe MariaDB + PHP-FPM + phpMyAdmin (accès /phpmyadmin/ style cPanel).
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
VZONE_USER="${VZONE_USER:-vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
DATA_ROOT="${VZONE_DATA_ROOT:-/var/lib/vzone}"
PMA_ROOT="${VZONE_PHPMYADMIN_ROOT:-/opt/vzone/phpmyadmin}"
SSO_DIR="${DATA_ROOT}/phpmyadmin/sso"

echo "[vzone] Installation phpMyAdmin + MariaDB + PHP-FPM"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  mariadb-server mariadb-client \
  php-fpm php-mysql php-mbstring php-xml php-curl php-zip php-gd php-intl \
  curl ca-certificates unzip

# MariaDB actif
systemctl enable --now mariadb 2>/dev/null || systemctl enable --now mysql

# Mot de passe admin panel pour provisionnement live
MYSQL_ADMIN_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
  if [[ -n "${VZONE_MYSQL_ADMIN_PASSWORD:-}" ]]; then
    MYSQL_ADMIN_PASS="${VZONE_MYSQL_ADMIN_PASSWORD}"
  fi
fi

mysql -e "CREATE USER IF NOT EXISTS 'vzone'@'localhost' IDENTIFIED BY '${MYSQL_ADMIN_PASS}';" 2>/dev/null \
  || mysql -e "CREATE USER 'vzone'@'localhost' IDENTIFIED BY '${MYSQL_ADMIN_PASS}';" 2>/dev/null \
  || true
mysql -e "ALTER USER 'vzone'@'localhost' IDENTIFIED BY '${MYSQL_ADMIN_PASS}';" 2>/dev/null || true
mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'vzone'@'localhost' WITH GRANT OPTION; FLUSH PRIVILEGES;" 2>/dev/null || true

# Déployer phpMyAdmin dans /opt/vzone/phpmyadmin
PMA_VERSION="5.2.2"
mkdir -p "$(dirname "$PMA_ROOT")" "$SSO_DIR"
if [[ ! -f "${PMA_ROOT}/index.php" ]]; then
  TMP="$(mktemp -d)"
  curl -fsSL "https://files.phpmyadmin.net/phpMyAdmin/${PMA_VERSION}/phpMyAdmin-${PMA_VERSION}-all-languages.tar.gz" \
    -o "${TMP}/pma.tar.gz"
  tar -xzf "${TMP}/pma.tar.gz" -C "$TMP"
  rm -rf "$PMA_ROOT"
  mv "${TMP}/phpMyAdmin-${PMA_VERSION}-all-languages" "$PMA_ROOT"
  rm -rf "$TMP"
fi

BLOWFISH="$(openssl rand -hex 32)"
install -m 640 "${REPO_DIR}/deploy/phpmyadmin/config.inc.php" "${PMA_ROOT}/config.inc.php"
sed -i "s|__BLOWFISH__|${BLOWFISH}|g" "${PMA_ROOT}/config.inc.php"
sed -i "s|__SSO_DIR__|${SSO_DIR}|g" "${PMA_ROOT}/config.inc.php"

install -m 644 "${REPO_DIR}/deploy/phpmyadmin/vzone-signon.php" "${PMA_ROOT}/vzone-signon.php"
install -m 644 "${REPO_DIR}/deploy/phpmyadmin/vzone-sso.php" "${PMA_ROOT}/vzone-sso.php"
sed -i "s|__SSO_DIR__|${SSO_DIR}|g" "${PMA_ROOT}/vzone-sso.php"

# Droits
chown -R root:www-data "$PMA_ROOT"
chmod -R a+rX "$PMA_ROOT"
chmod 640 "${PMA_ROOT}/config.inc.php"
mkdir -p "${PMA_ROOT}/tmp"
chown -R www-data:www-data "${PMA_ROOT}/tmp"
chmod 770 "${PMA_ROOT}/tmp"

mkdir -p "$SSO_DIR"
chown -R "${VZONE_USER}:www-data" "$(dirname "$SSO_DIR")"
chmod 770 "$SSO_DIR"

# PHP-FPM
PHP_SOCK="$(ls /run/php/php*-fpm.sock 2>/dev/null | head -n1 || true)"
if [[ -z "$PHP_SOCK" ]]; then
  systemctl enable --now php*-fpm 2>/dev/null || systemctl enable --now php8.1-fpm || systemctl enable --now php8.3-fpm || true
  PHP_SOCK="$(ls /run/php/php*-fpm.sock 2>/dev/null | head -n1 || true)"
fi
[[ -n "$PHP_SOCK" ]] || { echo "[vzone] Socket PHP-FPM introuvable"; exit 1; }
echo "[vzone] PHP-FPM socket: ${PHP_SOCK}"

# Snippet nginx
install -d /etc/nginx/snippets
install -m 644 "${REPO_DIR}/deploy/nginx/phpmyadmin.inc" /etc/nginx/snippets/vzone-phpmyadmin.inc
sed -i "s|__PMA_ROOT__|${PMA_ROOT}|g" /etc/nginx/snippets/vzone-phpmyadmin.inc
sed -i "s|__PHP_SOCK__|${PHP_SOCK}|g" /etc/nginx/snippets/vzone-phpmyadmin.inc

# Env panel
if [[ -f "$ENV_FILE" ]]; then
  grep -q '^VZONE_PHPMYADMIN_URL=' "$ENV_FILE" || echo "VZONE_PHPMYADMIN_URL=/phpmyadmin/" >> "$ENV_FILE"
  sed -i 's|^VZONE_PHPMYADMIN_URL=.*|VZONE_PHPMYADMIN_URL=/phpmyadmin/|' "$ENV_FILE"
  grep -q '^VZONE_PHPMYADMIN_ROOT=' "$ENV_FILE" || echo "VZONE_PHPMYADMIN_ROOT=${PMA_ROOT}" >> "$ENV_FILE"
  grep -q '^VZONE_MYSQL_HOST=' "$ENV_FILE" || echo "VZONE_MYSQL_HOST=127.0.0.1" >> "$ENV_FILE"
  if ! grep -q '^VZONE_MYSQL_ADMIN_USER=' "$ENV_FILE"; then
    echo "VZONE_MYSQL_ADMIN_USER=vzone" >> "$ENV_FILE"
  else
    sed -i 's|^VZONE_MYSQL_ADMIN_USER=.*|VZONE_MYSQL_ADMIN_USER=vzone|' "$ENV_FILE"
  fi
  if ! grep -q '^VZONE_MYSQL_ADMIN_PASSWORD=' "$ENV_FILE"; then
    echo "VZONE_MYSQL_ADMIN_PASSWORD=${MYSQL_ADMIN_PASS}" >> "$ENV_FILE"
  fi
  if ! grep -q '^VZONE_DB_PROVISION_MODE=' "$ENV_FILE"; then
    echo "VZONE_DB_PROVISION_MODE=live" >> "$ENV_FILE"
  else
    sed -i 's|^VZONE_DB_PROVISION_MODE=.*|VZONE_DB_PROVISION_MODE=live|' "$ENV_FILE"
  fi
  grep -q '^VZONE_PHPMYADMIN_SSO_DIR=' "$ENV_FILE" || echo "VZONE_PHPMYADMIN_SSO_DIR=${SSO_DIR}" >> "$ENV_FILE"
fi

# Recharge nginx via ensure (si conf déjà mise à jour avec include)
if nginx -t 2>/dev/null; then
  systemctl reload nginx || true
fi
systemctl reload php*-fpm 2>/dev/null || systemctl reload php8.1-fpm 2>/dev/null || true

echo "[vzone] phpMyAdmin OK → https://IP/phpmyadmin/ (ou /phpmyadmin/)"
echo "[vzone] MariaDB user panel : vzone (provision live)"
echo "[vzone] SSO tokens : ${SSO_DIR}"
