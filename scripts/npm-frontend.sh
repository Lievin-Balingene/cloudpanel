#!/usr/bin/env bash
# Sync sources + deps npm + build frontend V-zone (robuste face à ENOTEMPTY).
# Usage: bash scripts/npm-frontend.sh [/opt/vzone/frontend]
set -euo pipefail

FRONTEND_DIR="${1:-${VZONE_ROOT:-/opt/vzone}/frontend}"
REPO_DIR="${REPO_DIR:-/opt/vzone-src}"
SRC_FE=""
for candidate in \
  "${REPO_DIR}/frontend" \
  /opt/vzone-src/frontend \
  "$(cd "$(dirname "$0")/.." && pwd)/frontend"; do
  if [[ -f "${candidate}/package.json" ]]; then
    SRC_FE="$candidate"
    break
  fi
done

mkdir -p "$FRONTEND_DIR"

# Toujours resync le code source depuis le dépôt (sinon rebuild = ancien JS)
if [[ -n "$SRC_FE" && "$(cd "$SRC_FE" && pwd)" != "$(cd "$FRONTEND_DIR" && pwd 2>/dev/null || true)" ]]; then
  echo "[vzone] Sync frontend ${SRC_FE} → ${FRONTEND_DIR}"
  rsync -a \
    --exclude node_modules \
    --exclude dist \
    "${SRC_FE}/" "${FRONTEND_DIR}/"
fi

[[ -f "${FRONTEND_DIR}/package.json" ]] || {
  echo "[vzone] package.json manquant dans $FRONTEND_DIR" >&2
  exit 1
}

cd "$FRONTEND_DIR"

npm_install_deps() {
  if [[ -f package-lock.json ]]; then
    npm ci --no-audit --no-fund "$@"
  else
    npm install --no-audit --no-fund "$@"
  fi
}

echo "[vzone] npm deps → ${FRONTEND_DIR}"
if ! npm_install_deps; then
  echo "[vzone] npm a échoué (souvent ENOTEMPTY) — purge node_modules + retry…"
  rm -rf node_modules
  find . -maxdepth 1 -type d -name '.*' -name '*-*' 2>/dev/null \
    | while read -r d; do rm -rf "$d" 2>/dev/null || true; done
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
# Afficher le hash du bundle pour vérifier qu'un vrai rebuild a eu lieu
JS_BUNDLE="$(ls -1 "${FRONTEND_DIR}/dist/assets/"index-*.js 2>/dev/null | head -n1 || true)"
if [[ -n "$JS_BUNDLE" ]]; then
  echo "[vzone] Frontend OK → ${FRONTEND_DIR}/dist/index.html ($(basename "$JS_BUNDLE"))"
else
  echo "[vzone] Frontend OK → ${FRONTEND_DIR}/dist/index.html"
fi
