#!/usr/bin/env bash
# Bootstrap : clone le dépôt puis lance l'installateur V-zone Panel.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Lievin-Balingene/cloudpanel/main/scripts/bootstrap-install.sh | sudo bash
set -euo pipefail

REPO_URL="${VZONE_REPO_URL:-https://github.com/Lievin-Balingene/cloudpanel.git}"
SRC_DIR="${VZONE_SRC_DIR:-/opt/vzone-src}"
BRANCH="${VZONE_BRANCH:-main}"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "Exécutez en root (sudo)." >&2
  exit 1
fi

if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y git ca-certificates curl
elif command -v dnf >/dev/null 2>&1; then
  dnf -y install git ca-certificates curl
fi

if [[ -d "${SRC_DIR}/.git" ]]; then
  git -C "${SRC_DIR}" fetch --depth 1 origin "${BRANCH}"
  git -C "${SRC_DIR}" checkout "${BRANCH}"
  git -C "${SRC_DIR}" reset --hard "origin/${BRANCH}"
else
  rm -rf "${SRC_DIR}"
  git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${SRC_DIR}"
fi

cd "${SRC_DIR}"
bash scripts/install.sh "$@"
