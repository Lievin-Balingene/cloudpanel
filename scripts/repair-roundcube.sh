#!/usr/bin/env bash
# Diagnostic + réparation légère Roundcube (« Oops… something went wrong »).
# Usage: sudo bash /opt/vzone-src/scripts/repair-roundcube.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-/opt/vzone/roundcube}"

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-$RC_ROOT}"

echo "=== repair-roundcube ==="
echo "RC_ROOT=$RC_ROOT"

if [[ ! -d "$RC_ROOT" ]]; then
  echo "Roundcube absent — relance: bash ${REPO_DIR}/scripts/install-roundcube.sh"
  bash "${REPO_DIR}/scripts/install-roundcube.sh"
  exit $?
fi

echo
echo "[1] Dernières erreurs Roundcube"
if [[ -f "${RC_ROOT}/logs/errors.log" ]]; then
  tail -n 40 "${RC_ROOT}/logs/errors.log"
else
  echo "(pas de logs/errors.log)"
fi

echo
echo "[2] Config critique"
CFG="${RC_ROOT}/config/config.inc.php"
if [[ -f "$CFG" ]]; then
  if grep -q '__DB_DSN__\|__DES_KEY__\|__TEMP_DIR__' "$CFG"; then
    echo "ERREUR: placeholders non remplacés dans config.inc.php — réinstall Roundcube"
    bash "${REPO_DIR}/scripts/install-roundcube.sh"
  else
    echo "placeholders OK"
    grep -E "db_dsnw|imap_host|des_key|temp_dir|request_path" "$CFG" | sed 's/password=[^@]*/password=***/' || true
  fi
  # Forcer IMAP local plain
  sed -i "s|\$config\['imap_host'\] = '.*'|\$config['imap_host'] = '127.0.0.1:143'|" "$CFG" || true
  # MySQL via TCP 127.0.0.1 (évite soucis socket/localhost)
  sed -i "s|@localhost/|@127.0.0.1/|g" "$CFG" || true
  sed -i "s|@localhost:|@127.0.0.1:|g" "$CFG" || true
else
  echo "config absente — install"
  bash "${REPO_DIR}/scripts/install-roundcube.sh"
fi

echo
echo "[3] Droits temp/logs"
mkdir -p "${RC_ROOT}/temp" "${RC_ROOT}/logs"
chown -R www-data:www-data "${RC_ROOT}/temp" "${RC_ROOT}/logs"
chmod 770 "${RC_ROOT}/temp" "${RC_ROOT}/logs"

echo
echo "[4] SSO + nginx snippet (QUERY_STRING)"
SSO_DIR="${VZONE_ROUNDCUBE_SSO_DIR:-/var/lib/vzone/roundcube/sso}"
mkdir -p "$SSO_DIR"
chown vzone:www-data "$SSO_DIR" 2>/dev/null || chown www-data:www-data "$SSO_DIR"
chmod 2770 "$SSO_DIR"
if [[ -f "${REPO_DIR}/deploy/roundcube/vzone-sso.php" ]]; then
  install -m 644 "${REPO_DIR}/deploy/roundcube/vzone-sso.php" "${RC_ROOT}/vzone-sso.php"
  sed -i "s|__SSO_DIR__|${SSO_DIR}|g" "${RC_ROOT}/vzone-sso.php"
  echo "SSO PHP mis à jour (write_close + token fallback)"
fi
if [[ -f "${REPO_DIR}/deploy/nginx/roundcube.inc" ]]; then
  PHP_SOCK="$(ls /run/php/php*-fpm.sock 2>/dev/null | head -n1 || echo /run/php/php-fpm.sock)"
  install -m 644 "${REPO_DIR}/deploy/nginx/roundcube.inc" /etc/nginx/snippets/vzone-roundcube.inc
  RC_ESC="$(printf '%s' "$RC_ROOT" | sed 's|[&/]|\\&|g')"
  PHP_ESC="$(printf '%s' "$PHP_SOCK" | sed 's|[&/]|\\&|g')"
  sed -i "s|__RC_ROOT__|${RC_ESC}|g" /etc/nginx/snippets/vzone-roundcube.inc
  sed -i "s|__PHP_SOCK__|${PHP_ESC}|g" /etc/nginx/snippets/vzone-roundcube.inc
  echo "nginx roundcube.inc mis à jour"
  if nginx -t 2>/dev/null; then
    systemctl reload nginx || true
  fi
fi

echo
echo "[5] DB Roundcube"
RC_DB_USER="${VZONE_ROUNDCUBE_DB_USER:-roundcube}"
RC_DB_NAME="${VZONE_ROUNDCUBE_DB_NAME:-roundcube}"
RC_DB_PASS="${VZONE_ROUNDCUBE_DB_PASSWORD:-}"
if [[ -n "$RC_DB_PASS" ]]; then
  if mysql -u "$RC_DB_USER" -p"$RC_DB_PASS" -h 127.0.0.1 -N -e "SELECT COUNT(*) FROM \`${RC_DB_NAME}\`.session;" 2>/dev/null; then
    echo "DB session OK"
  else
    echo "DB KO — réinstall tables"
    bash "${REPO_DIR}/scripts/install-roundcube.sh"
  fi
else
  echo "VZONE_ROUNDCUBE_DB_PASSWORD absent de $ENV_FILE"
fi

systemctl reload php*-fpm 2>/dev/null || systemctl reload php8.1-fpm 2>/dev/null || systemctl reload php8.3-fpm 2>/dev/null || true
systemctl reload nginx 2>/dev/null || true

echo
echo "[6] Logs après fix (rechargez /webmail/ puis):"
echo "  tail -n 30 ${RC_ROOT}/logs/errors.log"
echo "=== done ==="
