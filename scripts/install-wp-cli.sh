#!/usr/bin/env bash
# Installe WP-CLI + dépendances PHP utiles pour WordPress.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

echo "[vzone] Installation WP-CLI / WordPress"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# PHP CLI + extensions courantes WP (idempotent si déjà présentes)
apt-get install -y -qq \
  curl ca-certificates \
  php-cli php-mysql php-xml php-mbstring php-curl php-zip php-gd php-intl \
  2>/dev/null || apt-get install -y -qq curl ca-certificates php-cli || true

TMP="$(mktemp)"
curl -fsSL -o "$TMP" https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar
php "$TMP" --info >/dev/null
install -m 755 "$TMP" /usr/local/bin/wp
rm -f "$TMP"

# Wrapper confort (même binaire)
ln -sfn /usr/local/bin/wp /usr/bin/wp 2>/dev/null || true

wp --info --allow-root || /usr/local/bin/wp --info --allow-root

# Tab completion (optionnel)
if [[ ! -f /etc/bash_completion.d/wp ]]; then
  curl -fsSL -o /etc/bash_completion.d/wp \
    https://raw.githubusercontent.com/wp-cli/wp-cli/v2.11.0/utils/wp-completion.bash \
    2>/dev/null || true
fi

echo "[vzone] WP-CLI OK → $(command -v wp || echo /usr/local/bin/wp)"
