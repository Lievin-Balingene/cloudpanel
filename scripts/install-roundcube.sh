#!/usr/bin/env bash
# Installe Roundcube Webmail (accès /webmail/ + SSO panel).
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
VZONE_USER="${VZONE_USER:-vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
DATA_ROOT="${VZONE_DATA_ROOT:-/var/lib/vzone}"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-/opt/vzone/roundcube}"
SSO_DIR="${DATA_ROOT}/roundcube/sso"
RC_VERSION="${VZONE_ROUNDCUBE_VERSION:-1.6.10}"

echo "[vzone] Installation Roundcube Webmail ${RC_VERSION}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  php-fpm php-mysql php-mbstring php-xml php-curl php-zip php-gd php-intl \
  php-imap php-ldap \
  curl ca-certificates unzip mariadb-client

# PHP-FPM
systemctl enable --now php*-fpm 2>/dev/null || systemctl enable --now php8.1-fpm 2>/dev/null || systemctl enable --now php8.3-fpm 2>/dev/null || true
PHP_SOCK="$(ls /run/php/php*-fpm.sock 2>/dev/null | head -n1 || true)"
if [[ -z "$PHP_SOCK" ]]; then
  echo "[vzone] Socket PHP-FPM introuvable — lancez d'abord install-phpmyadmin.sh ou installez php-fpm"
  exit 1
fi
echo "[vzone] PHP-FPM socket: ${PHP_SOCK}"

# MariaDB doit être dispo (souvent via install-phpmyadmin)
if ! command -v mysql >/dev/null 2>&1; then
  apt-get install -y -qq mariadb-server
  systemctl enable --now mariadb 2>/dev/null || systemctl enable --now mysql
fi

# Mot de passe DB Roundcube
RC_DB_PASS="${VZONE_ROUNDCUBE_DB_PASSWORD:-}"
if [[ -z "$RC_DB_PASS" ]]; then
  RC_DB_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
fi
RC_DB_USER="${VZONE_ROUNDCUBE_DB_USER:-roundcube}"
RC_DB_NAME="${VZONE_ROUNDCUBE_DB_NAME:-roundcube}"

mysql -e "CREATE DATABASE IF NOT EXISTS \`${RC_DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS '${RC_DB_USER}'@'localhost' IDENTIFIED BY '${RC_DB_PASS}';" 2>/dev/null \
  || mysql -e "CREATE USER '${RC_DB_USER}'@'localhost' IDENTIFIED BY '${RC_DB_PASS}';" 2>/dev/null \
  || true
mysql -e "ALTER USER '${RC_DB_USER}'@'localhost' IDENTIFIED BY '${RC_DB_PASS}';" 2>/dev/null || true
mysql -e "GRANT ALL PRIVILEGES ON \`${RC_DB_NAME}\`.* TO '${RC_DB_USER}'@'localhost'; FLUSH PRIVILEGES;"

# Télécharger Roundcube
mkdir -p "$(dirname "$RC_ROOT")" "$SSO_DIR"
NEED_EXTRACT=0
if [[ ! -f "${RC_ROOT}/index.php" ]]; then
  NEED_EXTRACT=1
elif ! grep -q "Roundcube" "${RC_ROOT}/index.php" 2>/dev/null; then
  NEED_EXTRACT=1
fi

if [[ "$NEED_EXTRACT" -eq 1 ]]; then
  TMP="$(mktemp -d)"
  ARCHIVE="roundcubemail-${RC_VERSION}-complete.tar.gz"
  URL="https://github.com/roundcube/roundcubemail/releases/download/${RC_VERSION}/${ARCHIVE}"
  echo "[vzone] Téléchargement ${URL}"
  if ! curl -fsSL "$URL" -o "${TMP}/rc.tar.gz"; then
    URL="https://github.com/roundcube/roundcubemail/releases/download/${RC_VERSION}/roundcubemail-${RC_VERSION}.tar.gz"
    curl -fsSL "$URL" -o "${TMP}/rc.tar.gz"
  fi
  tar -xzf "${TMP}/rc.tar.gz" -C "$TMP"
  SRC_DIR="$(find "$TMP" -maxdepth 1 -type d -name 'roundcubemail-*' | head -n1)"
  [[ -n "$SRC_DIR" ]] || { echo "[vzone] Archive Roundcube invalide"; exit 1; }
  rm -rf "$RC_ROOT"
  mv "$SRC_DIR" "$RC_ROOT"
  rm -rf "$TMP"
fi

# Import schéma SQL si tables absentes (sans préfixe : session, users, …)
HAS_SESSION="$(mysql -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${RC_DB_NAME}' AND table_name='session';" 2>/dev/null || echo 0)"
TABLE_COUNT="$(mysql -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${RC_DB_NAME}';" 2>/dev/null || echo 0)"
if [[ "${HAS_SESSION}" -lt 1 ]] || [[ "${TABLE_COUNT}" -lt 5 ]]; then
  if [[ -f "${RC_ROOT}/SQL/mysql.initial.sql" ]]; then
    echo "[vzone] Import schéma Roundcube (tables manquantes)"
    mysql "${RC_DB_NAME}" < "${RC_ROOT}/SQL/mysql.initial.sql"
  fi
fi
# Tables orphelines rc_* (ancienne config db_prefix) sans table session → réimport stock
HAS_SESSION="$(mysql -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${RC_DB_NAME}' AND table_name='session';" 2>/dev/null || echo 0)"
HAS_RC_SESSION="$(mysql -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${RC_DB_NAME}' AND table_name='rc_session';" 2>/dev/null || echo 0)"
if [[ "${HAS_SESSION}" -lt 1 ]] && [[ "${HAS_RC_SESSION}" -gt 0 ]]; then
  echo "[vzone] Tables préfixées rc_* détectées — réimport schéma sans préfixe"
  mysql -e "DROP DATABASE IF EXISTS \`${RC_DB_NAME}\`; CREATE DATABASE \`${RC_DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
  mysql -e "GRANT ALL PRIVILEGES ON \`${RC_DB_NAME}\`.* TO '${RC_DB_USER}'@'localhost'; FLUSH PRIVILEGES;"
  mysql "${RC_DB_NAME}" < "${RC_ROOT}/SQL/mysql.initial.sql"
fi

DES_KEY="$(openssl rand -base64 18 | tr -d '/+=' | head -c 24)"
if [[ -f "${RC_ROOT}/config/config.inc.php" ]]; then
  OLD_DES="$(
    RC_ROOT="$RC_ROOT" python3 - <<'PY'
import os, re
from pathlib import Path
p = Path(os.environ["RC_ROOT"]) / "config" / "config.inc.php"
t = p.read_text(encoding="utf-8", errors="ignore")
m = re.search(r"\['des_key'\]\s*=\s*'([^']{24})'", t)
print(m.group(1) if m else "")
PY
  )"
  [[ ${#OLD_DES} -eq 24 ]] && DES_KEY="$OLD_DES"
fi
TEMP_DIR="${RC_ROOT}/temp"
mkdir -p "$TEMP_DIR" "${RC_ROOT}/logs"
# Mot de passe URL-encodé pour le DSN PHP
RC_DB_PASS_ENC="$(python3 -c "import urllib.parse; print(urllib.parse.quote('''${RC_DB_PASS}''', safe=''))" 2>/dev/null || printf '%s' "$RC_DB_PASS")"
DSN="mysql://${RC_DB_USER}:${RC_DB_PASS_ENC}@127.0.0.1/${RC_DB_NAME}"

install -m 640 "${REPO_DIR}/deploy/roundcube/config.inc.php" "${RC_ROOT}/config/config.inc.php"
# Échapper pour sed
DSN_ESC="$(printf '%s' "$DSN" | sed 's|[&/]|\\&|g')"
TEMP_ESC="$(printf '%s' "$TEMP_DIR" | sed 's|[&/]|\\&|g')"
sed -i "s|__DB_DSN__|${DSN_ESC}|g" "${RC_ROOT}/config/config.inc.php"
sed -i "s|__DES_KEY__|${DES_KEY}|g" "${RC_ROOT}/config/config.inc.php"
sed -i "s|__TEMP_DIR__|${TEMP_ESC}|g" "${RC_ROOT}/config/config.inc.php"

install -m 644 "${REPO_DIR}/deploy/roundcube/vzone-sso.php" "${RC_ROOT}/vzone-sso.php"
SSO_ESC="$(printf '%s' "$SSO_DIR" | sed 's|[&/]|\\&|g')"
sed -i "s|__SSO_DIR__|${SSO_ESC}|g" "${RC_ROOT}/vzone-sso.php"

# Droits
chown -R root:www-data "$RC_ROOT"
chmod -R a+rX "$RC_ROOT"
chmod 640 "${RC_ROOT}/config/config.inc.php"
chown -R www-data:www-data "$TEMP_DIR" "${RC_ROOT}/logs"
chmod 770 "$TEMP_DIR" "${RC_ROOT}/logs"

mkdir -p "$SSO_DIR"
chown -R "${VZONE_USER}:www-data" "$(dirname "$SSO_DIR")"
chmod 770 "$SSO_DIR"
chmod 770 "$(dirname "$SSO_DIR")" 2>/dev/null || true

# Désactiver l'installeur public
rm -rf "${RC_ROOT}/installer" 2>/dev/null || true

# Snippet nginx
install -d /etc/nginx/snippets
install -m 644 "${REPO_DIR}/deploy/nginx/roundcube.inc" /etc/nginx/snippets/vzone-roundcube.inc
RC_ESC="$(printf '%s' "$RC_ROOT" | sed 's|[&/]|\\&|g')"
PHP_ESC="$(printf '%s' "$PHP_SOCK" | sed 's|[&/]|\\&|g')"
sed -i "s|__RC_ROOT__|${RC_ESC}|g" /etc/nginx/snippets/vzone-roundcube.inc
sed -i "s|__PHP_SOCK__|${PHP_ESC}|g" /etc/nginx/snippets/vzone-roundcube.inc

# Env panel
if [[ -f "$ENV_FILE" ]]; then
  grep -q '^VZONE_WEBMAIL_URL=' "$ENV_FILE" || echo "VZONE_WEBMAIL_URL=/webmail/" >> "$ENV_FILE"
  sed -i 's|^VZONE_WEBMAIL_URL=.*|VZONE_WEBMAIL_URL=/webmail/|' "$ENV_FILE"
  grep -q '^VZONE_ROUNDCUBE_ROOT=' "$ENV_FILE" || echo "VZONE_ROUNDCUBE_ROOT=${RC_ROOT}" >> "$ENV_FILE"
  sed -i "s|^VZONE_ROUNDCUBE_ROOT=.*|VZONE_ROUNDCUBE_ROOT=${RC_ROOT}|" "$ENV_FILE"
  grep -q '^VZONE_ROUNDCUBE_SSO_DIR=' "$ENV_FILE" || echo "VZONE_ROUNDCUBE_SSO_DIR=${SSO_DIR}" >> "$ENV_FILE"
  sed -i "s|^VZONE_ROUNDCUBE_SSO_DIR=.*|VZONE_ROUNDCUBE_SSO_DIR=${SSO_DIR}|" "$ENV_FILE"
  if grep -q '^VZONE_ROUNDCUBE_DB_PASSWORD=' "$ENV_FILE"; then
    sed -i "s|^VZONE_ROUNDCUBE_DB_PASSWORD=.*|VZONE_ROUNDCUBE_DB_PASSWORD=${RC_DB_PASS}|" "$ENV_FILE"
  else
    echo "VZONE_ROUNDCUBE_DB_PASSWORD=${RC_DB_PASS}" >> "$ENV_FILE"
  fi
  grep -q '^VZONE_ROUNDCUBE_DB_USER=' "$ENV_FILE" || echo "VZONE_ROUNDCUBE_DB_USER=${RC_DB_USER}" >> "$ENV_FILE"
  grep -q '^VZONE_ROUNDCUBE_DB_NAME=' "$ENV_FILE" || echo "VZONE_ROUNDCUBE_DB_NAME=${RC_DB_NAME}" >> "$ENV_FILE"
fi

# Vérifier la connexion DB avec le DSN final
if ! mysql -u "${RC_DB_USER}" -p"${RC_DB_PASS}" -N -e "SELECT 1 FROM \`${RC_DB_NAME}\`.session LIMIT 1;" >/dev/null 2>&1; then
  echo "[vzone] ATTENTION: connexion Roundcube DB ou table session KO — vérifiez /opt/vzone/roundcube/logs/errors.log"
else
  echo "[vzone] DB Roundcube OK (table session présente)"
fi

if nginx -t 2>/dev/null; then
  systemctl reload nginx || true
fi
systemctl reload php*-fpm 2>/dev/null || systemctl reload php8.1-fpm 2>/dev/null || systemctl reload php8.3-fpm 2>/dev/null || true

echo "[vzone] Roundcube OK → /webmail/ (SSO panel via vzone-sso.php)"
echo "[vzone] IMAP 127.0.0.1:143 · SMTP tls://127.0.0.1:587 (identifiant = adresse e-mail complète)"
