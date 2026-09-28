#!/usr/bin/env bash
# Installe les deps npm + build le frontend V-zone (robuste face à ENOTEMPTY).
# Usage: bash scripts/npm-frontend.sh [/opt/vzone/frontend]
set -euo pipefail

FRONTEND_DIR="${1:-${VZONE_ROOT:-/opt/vzone}/frontend}"
[[ -d "$FRONTEND_DIR" ]] || { echo "[vzone] Frontend introuvable: $FRONTEND_DIR" >&2; exit 1; }
[[ -f "${FRONTEND_DIR}/package.json" ]] || {
  echo "[vzone] package.json manquant dans $FRONTEND_DIR" >&2
  exit 1
}

cd "$FRONTEND_DIR"

npm_install_deps() {
  # --prefer-offline accélère ; --no-fund évite le bruit CI
  if [[ -f package-lock.json ]]; then
    npm ci --no-audit --no-fund "$@"
  else
    npm install --no-audit --no-fund "$@"
  fi
}

echo "[vzone] npm deps → ${FRONTEND_DIR}"
if ! npm_install_deps; then
  echo "[vzone] npm a échoué (souvent ENOTEMPTY) — purge node_modules + retry…"
  # Sur certains FS (overlay/rsync), rmdir échoue si des fichiers fantômes restent
  rm -rf node_modules
  # Dossiers de rename npm (.pkg-XXXX) laissés par un install interrompu
  find . -maxdepth 1 -type d -name '.*' -name '*-*' 2>/dev/null \
    | while read -r d; do rm -rf "$d" 2>/dev/null || true; done
  # Cache npm local du projet si présent
  rm -rf .npm 2>/dev/null || true

  if ! npm_install_deps; then
    echo "[vzone] 2e échec npm — purge + cache npm clean…"
    rm -rf node_modules
    npm cache clean --force 2>/dev/null || true
    npm_install_deps
  fi
fi

echo "[vzone] npm run build…"
npm run build

if [[ ! -f "${FRONTEND_DIR}/dist/index.html" ]]; then
  echo "[vzone] ERREUR: ${FRONTEND_DIR}/dist/index.html manquant après build" >&2
  exit 1
fi

chmod -R a+rX "${FRONTEND_DIR}/dist" || true
echo "[vzone] Frontend OK → ${FRONTEND_DIR}/dist/index.html"
