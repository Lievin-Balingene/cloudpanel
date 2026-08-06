#!/usr/bin/env bash
# Répare Roundcube « Oops… something went wrong » (souvent config.inc.php cassée).
# Usage: sudo bash /opt/vzone-src/scripts/repair-roundcube.sh
set -uo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-/opt/vzone/roundcube}"

if [[ -f "$ENV_FILE" ]]; then
  set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a
fi
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-$RC_ROOT}"
CFG="${RC_ROOT}/config/config.inc.php"

echo "=== repair-roundcube (0.32.11) ==="
echo "RC_ROOT=$RC_ROOT"

if [[ ! -d "$RC_ROOT" ]] || [[ ! -f "${RC_ROOT}/index.php" ]]; then
  bash "${REPO_DIR}/scripts/install-roundcube.sh"
  exit $?
fi

echo
echo "[1] Dernières erreurs"
tail -n 50 "${RC_ROOT}/logs/errors.log" 2>/dev/null || echo "(pas de errors.log)"

echo
echo "[2] Vérification PHP config"
BROKEN=0
if [[ ! -f "$CFG" ]]; then
  BROKEN=1
elif ! php -l "$CFG" >/tmp/vzone-rc-lint.txt 2>&1; then
  echo "CONFIG CASSÉE:"
  cat /tmp/vzone-rc-lint.txt
  BROKEN=1
elif grep -qE '__DB_DSN__|__DES_KEY__|__TEMP_DIR__' "$CFG"; then
  echo "Placeholders non remplacés"
  BROKEN=1
elif grep -qE 'repair-smtp|^\s*\]\s*;\s*$' "$CFG" && ! php -l "$CFG" >/dev/null 2>&1; then
  BROKEN=1
fi

# Si le repair-smtp a laissé des blocs orphelins / doublons dangereux → réinstall config
if grep -c "smtp_host" "$CFG" 2>/dev/null | grep -vq '^1$'; then
  echo "Plusieurs smtp_host détectés — réécriture"
  BROKEN=1
fi

if [[ "$BROKEN" -eq 1 ]]; then
  echo "[2b] Régénération via install-roundcube.sh (préserve DB)…"
  cp -a "$CFG" "${CFG}.broken.$(date +%s)" 2>/dev/null || true
  bash "${REPO_DIR}/scripts/install-roundcube.sh"
else
  echo "Syntaxe OK"
  # Assurer SMTP tls sans tout casser
  if ! grep -q "tls://127.0.0.1:587" "$CFG"; then
    # Remplacer une ligne smtp_host simple si présente
    if grep -q "\$config\['smtp_host'\]" "$CFG"; then
      sed -i "s|\$config\['smtp_host'\] = '.*'|\$config['smtp_host'] = 'tls://127.0.0.1:587'|" "$CFG"
      sed -i "s|\$config\['smtp_user'\] = '.*'|\$config['smtp_user'] = '%u'|" "$CFG" || true
      sed -i "s|\$config\['smtp_pass'\] = '.*'|\$config['smtp_pass'] = '%p'|" "$CFG" || true
    fi
  fi
  php -l "$CFG"
fi

echo
echo "[3] Droits + SSO + nginx"
mkdir -p "${RC_ROOT}/temp" "${RC_ROOT}/logs"
chown -R www-data:www-data "${RC_ROOT}/temp" "${RC_ROOT}/logs"
chmod 770 "${RC_ROOT}/temp" "${RC_ROOT}/logs"

SSO_DIR="${VZONE_ROUNDCUBE_SSO_DIR:-/var/lib/vzone/roundcube/sso}"
mkdir -p "$SSO_DIR"
chown vzone:www-data "$SSO_DIR" 2>/dev/null || chown www-data:www-data "$SSO_DIR"
chmod 2770 "$SSO_DIR"
if [[ -f "${REPO_DIR}/deploy/roundcube/vzone-sso.php" ]]; then
  install -m 644 "${REPO_DIR}/deploy/roundcube/vzone-sso.php" "${RC_ROOT}/vzone-sso.php"
  sed -i "s|__SSO_DIR__|${SSO_DIR}|g" "${RC_ROOT}/vzone-sso.php"
fi
if [[ -f "${REPO_DIR}/deploy/nginx/roundcube.inc" ]]; then
  PHP_SOCK="$(ls /run/php/php*-fpm.sock 2>/dev/null | head -n1 || echo /run/php/php-fpm.sock)"
  install -m 644 "${REPO_DIR}/deploy/nginx/roundcube.inc" /etc/nginx/snippets/vzone-roundcube.inc
  RC_ESC="$(printf '%s' "$RC_ROOT" | sed 's|[&/]|\\&|g')"
  PHP_ESC="$(printf '%s' "$PHP_SOCK" | sed 's|[&/]|\\&|g')"
  sed -i "s|__RC_ROOT__|${RC_ESC}|g" /etc/nginx/snippets/vzone-roundcube.inc
  sed -i "s|__PHP_SOCK__|${PHP_ESC}|g" /etc/nginx/snippets/vzone-roundcube.inc
  nginx -t 2>/dev/null && systemctl reload nginx || true
fi

systemctl restart php8.1-fpm 2>/dev/null || systemctl restart php8.2-fpm 2>/dev/null || systemctl restart php8.3-fpm 2>/dev/null || true

echo
echo "[4] État final"
php -l "$CFG" || true
grep -n "smtp_host\|smtp_user\|db_dsnw\|des_key" "$CFG" | sed 's/password=[^@]*/password=***/' | head -n 15

echo
echo "=== Ctrl+F5 sur /webmail/ ==="
echo "Si Oops: tail -n 30 ${RC_ROOT}/logs/errors.log"
echo "=== repair-roundcube OK ==="
