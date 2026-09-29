#!/usr/bin/env bash
# Source unique des droits SSO Roundcube — idempotent, sûr à relancer à chaque update.
# PHP-FPM (www-data) DOIT pouvoir lire/rename les tokens écrits par Django (vzone).
#
# Usage: sudo bash /opt/vzone-src/scripts/ensure-roundcube-sso.sh
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
VZONE_USER="${VZONE_USER:-vzone}"
DATA_ROOT="${VZONE_DATA_ROOT:-/var/lib/vzone}"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-/opt/vzone/roundcube}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi
DATA_ROOT="${VZONE_DATA_ROOT:-$DATA_ROOT}"
RC_ROOT="${VZONE_ROUNDCUBE_ROOT:-$RC_ROOT}"

# Chemin canonique : sous temp Roundcube (déjà servi par PHP / www-data).
# Évite /var/lib/vzone (souvent vzone:vzone 750 → www-data ne traverse pas).
SSO_DIR="${RC_ROOT}/temp/sso"
LEGACY_SSO="${DATA_ROOT}/roundcube/sso"

echo "[ensure-roundcube-sso] RC_ROOT=${RC_ROOT}"
echo "[ensure-roundcube-sso] SSO_DIR=${SSO_DIR}"

mkdir -p "${RC_ROOT}/temp" "${RC_ROOT}/logs" "$SSO_DIR"
# temp/logs : PHP
chown -R www-data:www-data "${RC_ROOT}/temp" "${RC_ROOT}/logs" 2>/dev/null || true
chmod 1777 "${RC_ROOT}/temp" 2>/dev/null || chmod 777 "${RC_ROOT}/temp" || true
# SSO : sticky world-writable — Django (vzone) ET PHP (www-data) écrivent/lisent/rename
# sans dépendre des groupes supplémentaires du process gunicorn.
chmod 1777 "$SSO_DIR"
chown www-data:www-data "$SSO_DIR" 2>/dev/null || true

# Legacy : rendre traversable + migrer éventuellement, puis même mode 1777
if [[ -d "$DATA_ROOT" ]]; then
  # www-data doit pouvoir traverser /var/lib/vzone si un vieux token y pointe encore
  chmod a+x "$DATA_ROOT" 2>/dev/null || true
  if [[ -d "${DATA_ROOT}/roundcube" ]]; then
    chmod a+x "${DATA_ROOT}/roundcube" 2>/dev/null || true
  fi
fi
if [[ -d "$LEGACY_SSO" ]]; then
  chmod 1777 "$LEGACY_SSO" 2>/dev/null || true
  # Déplacer d'éventuels tokens frais vers le chemin canonique
  find "$LEGACY_SSO" -maxdepth 1 -type f \( -name '*.json' -o -name '*.json.used' \) \
    -mmin -5 -exec mv -f {} "$SSO_DIR"/ \; 2>/dev/null || true
fi

# vzone dans www-data (bénéfique pour d'autres chemins)
usermod -aG www-data "${VZONE_USER}" 2>/dev/null || true

# Installer / rafraîchir vzone-sso.php avec le bon __SSO_DIR__
if [[ -d "$RC_ROOT" ]]; then
  SRC_SSO="${REPO_DIR}/deploy/roundcube/vzone-sso.php"
  if [[ -f "$SRC_SSO" ]]; then
    install -m 644 "$SRC_SSO" "${RC_ROOT}/vzone-sso.php"
  fi
  if [[ -f "${RC_ROOT}/vzone-sso.php" ]]; then
    # Remplace le placeholder OU un ancien chemin absolu hardcodé
    if grep -q '__SSO_DIR__' "${RC_ROOT}/vzone-sso.php" 2>/dev/null; then
      SSO_ESC="$(printf '%s' "$SSO_DIR" | sed 's|[&/]|\\&|g')"
      sed -i "s|__SSO_DIR__|${SSO_ESC}|g" "${RC_ROOT}/vzone-sso.php"
    else
      # Force le chemin canonique même si un update a laissé un vieux path
      python3 - "$SSO_DIR" "${RC_ROOT}/vzone-sso.php" <<'PY'
import sys
from pathlib import Path
sso, path = sys.argv[1], Path(sys.argv[2])
text = path.read_text(encoding="utf-8", errors="replace")
import re
new, n = re.subn(
    r"\$ssoDir\s*=\s*'[^']*'\s*;",
    f"$ssoDir = '{sso}';",
    text,
    count=1,
)
if n:
    path.write_text(new, encoding="utf-8")
    print(f"[ensure-roundcube-sso] vzone-sso.php → {sso}")
else:
    print("[ensure-roundcube-sso] avertissement: \$ssoDir non trouvé dans vzone-sso.php")
PY
    fi
    chown root:www-data "${RC_ROOT}/vzone-sso.php" 2>/dev/null || true
    chmod 644 "${RC_ROOT}/vzone-sso.php"
  fi
fi

# Persister dans l'env panel (Django lit ça)
mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"
if grep -q '^VZONE_ROUNDCUBE_SSO_DIR=' "$ENV_FILE" 2>/dev/null; then
  sed -i "s|^VZONE_ROUNDCUBE_SSO_DIR=.*|VZONE_ROUNDCUBE_SSO_DIR=${SSO_DIR}|" "$ENV_FILE"
else
  echo "VZONE_ROUNDCUBE_SSO_DIR=${SSO_DIR}" >> "$ENV_FILE"
fi
if grep -q '^VZONE_ROUNDCUBE_ROOT=' "$ENV_FILE" 2>/dev/null; then
  sed -i "s|^VZONE_ROUNDCUBE_ROOT=.*|VZONE_ROUNDCUBE_ROOT=${RC_ROOT}|" "$ENV_FILE"
else
  echo "VZONE_ROUNDCUBE_ROOT=${RC_ROOT}" >> "$ENV_FILE"
fi

# Test d'accès réel (simule PHP + Django)
TMP_TOKEN="${SSO_DIR}/.ensure-test.$$"
echo '{"ok":1}' > "$TMP_TOKEN"
chmod 666 "$TMP_TOKEN"
# Lecture en tant que www-data
if runuser -u www-data -- test -r "$TMP_TOKEN" 2>/dev/null \
  || su -s /bin/bash www-data -c "test -r '$TMP_TOKEN'" 2>/dev/null \
  || sudo -u www-data test -r "$TMP_TOKEN" 2>/dev/null; then
  echo "[ensure-roundcube-sso] OK www-data lit le token"
else
  echo "[ensure-roundcube-sso] WARN: test www-data illisible — chmod 1777 forcé"
  chmod 1777 "$SSO_DIR"
  chmod 666 "$TMP_TOKEN" || true
fi
# Rename (consommation SSO)
if mv "$TMP_TOKEN" "${TMP_TOKEN}.used" 2>/dev/null; then
  rm -f "${TMP_TOKEN}.used"
  echo "[ensure-roundcube-sso] OK rename (consume) fonctionne"
else
  echo "[ensure-roundcube-sso] ERR rename impossible sur ${SSO_DIR}"
  ls -la "$(dirname "$SSO_DIR")" "$SSO_DIR" || true
  exit 1
fi

# Nettoyage tokens vieux
find "$SSO_DIR" -type f \( -name '*.json' -o -name '*.json.used' -o -name '.ensure-test*' \) \
  -mmin +30 -delete 2>/dev/null || true

echo "[ensure-roundcube-sso] terminé — SSO_DIR=${SSO_DIR} (mode $(stat -c '%a' "$SSO_DIR" 2>/dev/null || echo '?'))"
