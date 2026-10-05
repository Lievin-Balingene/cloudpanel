#!/usr/bin/env bash
# Installe TOUS les helpers panel (runas, fix-perms, kill-port, sudoers…) — jour 0.
# Idempotent. Appelé par install.sh, update.sh et post-install-bootstrap.sh.
# Usage: sudo bash scripts/ensure-panel-helpers.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
VZONE_USER="${VZONE_USER:-vzone}"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "Root requis" >&2
  exit 1
fi

log() { printf '\033[1;34m[helpers]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }

# Préférer scripts du dépôt source si on est encore dans le clone
if [[ ! -f "${SCRIPT_DIR}/ensure-mkhome-sudoers.sh" && -f "${VZONE_ROOT}/scripts/ensure-mkhome-sudoers.sh" ]]; then
  SCRIPT_DIR="${VZONE_ROOT}/scripts"
  REPO_DIR="${VZONE_ROOT}"
fi

# ---------------------------------------------------------------------------
# Dépendances OS (fuser / ss / lsof) — requises pour kill-port
# ---------------------------------------------------------------------------
log "Dépendances OS (psmisc, iproute2, lsof)…"
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get install -y -qq psmisc iproute2 lsof util-linux >/dev/null 2>&1 \
    || warn "apt install psmisc/iproute2/lsof partiel"
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y -q psmisc iproute lsof util-linux >/dev/null 2>&1 \
    || warn "dnf install psmisc/iproute/lsof partiel"
elif command -v yum >/dev/null 2>&1; then
  yum install -y -q psmisc iproute lsof util-linux >/dev/null 2>&1 \
    || warn "yum install psmisc/iproute/lsof partiel"
fi

# ---------------------------------------------------------------------------
# Helpers + sudoers (mkhome, jailterm, runas, fix-app-perms, kill-port, …)
# ---------------------------------------------------------------------------
if [[ -f "${SCRIPT_DIR}/ensure-mkhome-sudoers.sh" ]]; then
  log "ensure-mkhome-sudoers (helpers + /etc/sudoers.d/vzone-panel)…"
  bash "${SCRIPT_DIR}/ensure-mkhome-sudoers.sh"
else
  warn "ensure-mkhome-sudoers.sh manquant"
fi

# Copie de secours si un helper manque encore
missing=0
while IFS='|' read -r bin srcname; do
  [[ -z "$bin" ]] && continue
  src="${SCRIPT_DIR}/${srcname}"
  dest="/usr/local/sbin/${bin}"
  if [[ -f "$src" ]]; then
    install -m 755 "$src" "$dest"
  fi
  if [[ ! -x "$dest" ]]; then
    warn "Helper manquant: ${dest}"
    missing=$((missing + 1))
  else
    ok "${bin}"
  fi
done <<'EOF'
vzone-mkhome|vzone-mkhome.sh
vzone-jailterm|vzone-jailterm.sh
vzone-rootterm|vzone-rootterm.sh
vzone-runas|vzone-runas.sh
vzone-fix-app-perms|vzone-fix-app-perms.sh
vzone-kill-port|vzone-kill-port.sh
vzone-smtp-restrictions|vzone-smtp-restrictions.sh
vzone-resourcectl|vzone-resourcectl.sh
vzone-svcctl|vzone-svcctl.sh
EOF

# Sudoers (au cas où ensure-mkhome a échoué avant la copie)
if [[ -f "${REPO_DIR}/deploy/sudoers/vzone-panel" ]]; then
  install -m 440 "${REPO_DIR}/deploy/sudoers/vzone-panel" /etc/sudoers.d/vzone-panel
  if ! visudo -cf /etc/sudoers.d/vzone-panel >/dev/null 2>&1; then
    warn "sudoers vzone-panel invalide — rollback"
    rm -f /etc/sudoers.d/vzone-panel
    missing=$((missing + 1))
  else
    ok "sudoers vzone-panel (kill-port, runas, fix-perms…)"
  fi
fi

# Terminal sudoers (si présent)
if [[ -f "${SCRIPT_DIR}/ensure-terminal-sudoers.sh" ]]; then
  bash "${SCRIPT_DIR}/ensure-terminal-sudoers.sh" || warn "ensure-terminal-sudoers a échoué"
fi

# ---------------------------------------------------------------------------
# Smoke-tests (vzone → sudo -n helpers)
# ---------------------------------------------------------------------------
if id -u "${VZONE_USER}" >/dev/null 2>&1; then
  if command -v runuser >/dev/null 2>&1; then
    if runuser -u "${VZONE_USER}" -- sudo -n /usr/local/sbin/vzone-kill-port 29998 >/dev/null 2>&1; then
      ok "smoke-test kill-port (sudo -n)"
    else
      warn "smoke-test kill-port échoué — vérifiez /etc/sudoers.d/vzone-panel et NoNewPrivileges=false"
    fi
  elif su -s /bin/bash "${VZONE_USER}" -c "sudo -n /usr/local/sbin/vzone-kill-port 29998" >/dev/null 2>&1; then
    ok "smoke-test kill-port (sudo -n via su)"
  else
    warn "smoke-test kill-port échoué"
  fi
fi

if [[ "$missing" -gt 0 ]]; then
  warn "Helpers incomplets (${missing}) — relancez: sudo bash ${SCRIPT_DIR}/ensure-panel-helpers.sh"
  exit 1
fi

ok "Tous les helpers panel sont en place (install jour 0)"
exit 0
