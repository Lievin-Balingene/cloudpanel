#!/usr/bin/env bash
# V-zone — bootstrap post-install : installe TOUS les modules puis répare la stack.
# Appelé par install.sh ; utilisable aussi seul après une install partielle :
#   sudo bash /opt/vzone/scripts/post-install-bootstrap.sh
#   sudo bash scripts/post-install-bootstrap.sh --repair-only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
VZONE_DATA="${VZONE_DATA:-/var/lib/vzone}"
VZONE_USER="${VZONE_USER:-vzone}"
REPAIR_ONLY=0
SKIP_HEAVY=0

for arg in "$@"; do
  case "$arg" in
    --repair-only) REPAIR_ONLY=1 ;;
    --skip-heavy) SKIP_HEAVY=1 ;;
  esac
done

# Préférer le dépôt déployé s'il existe
if [[ -d "${VZONE_ROOT}/scripts" ]]; then
  SCRIPT_DIR="${VZONE_ROOT}/scripts"
  REPO_DIR="${VZONE_ROOT}"
fi

log()  { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
step() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }

run_ok() {
  local label="$1"; shift
  log "→ ${label}"
  if "$@"; then
    ok "${label}"
    return 0
  fi
  warn "${label} a échoué (on continue)"
  return 0
}

require_root() {
  [[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }
}

load_env() {
  if [[ -f /etc/vzone/vzone.env ]]; then
    set -a
    # shellcheck disable=SC1091
    source /etc/vzone/vzone.env
    set +a
  fi
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-vzone.settings.production}"
  export VZONE_ROOT VZONE_DATA VZONE_USER
}

# ---------------------------------------------------------------------------
# Installations modules (idempotentes)
# ---------------------------------------------------------------------------
install_all_modules() {
  step "Installation / mise à jour de tous les modules"

  local scripts=(
    install-mail.sh
    install-phpmyadmin.sh
    install-postgresql.sh
    install-roundcube.sh
    install-certbot.sh
    install-cron.sh
    install-hostname-agent.sh
    install-wp-cli.sh
    install-repair-agent.sh
    install-update-agent.sh
  )

  if [[ "${VZONE_OLS_ENABLED:-1}" =~ ^(1|true|TRUE|yes|YES)$ ]]; then
    scripts+=(install-openlitespeed.sh)
  fi
  if [[ "${SKIP_HEAVY}" != "1" ]]; then
    scripts+=(install-kubernetes.sh)
  fi

  local s
  for s in "${scripts[@]}"; do
    if [[ -f "${SCRIPT_DIR}/${s}" ]]; then
      run_ok "${s}" bash "${SCRIPT_DIR}/${s}"
    else
      warn "Script manquant: ${s}"
    fi
  done

  # Agents nginx reload / sudoers homes / terminal
  [[ -f "${SCRIPT_DIR}/ensure-nginx-reload-agent.sh" ]] && run_ok "nginx-reload-agent" bash "${SCRIPT_DIR}/ensure-nginx-reload-agent.sh"
  [[ -f "${SCRIPT_DIR}/ensure-mkhome-sudoers.sh" ]] && run_ok "mkhome-sudoers" bash "${SCRIPT_DIR}/ensure-mkhome-sudoers.sh"
  [[ -f "${SCRIPT_DIR}/repair-python-apps.sh" ]] && run_ok "repair-python-apps" bash "${SCRIPT_DIR}/repair-python-apps.sh"
  [[ -f "${SCRIPT_DIR}/ensure-terminal-sudoers.sh" ]] && run_ok "terminal-sudoers" bash "${SCRIPT_DIR}/ensure-terminal-sudoers.sh"
  [[ -f "${SCRIPT_DIR}/ensure-dns.sh" ]] && run_ok "ensure-dns" bash "${SCRIPT_DIR}/ensure-dns.sh"
}

# ---------------------------------------------------------------------------
# Django : migrate + seed packages + ACL revendeurs existants
# ---------------------------------------------------------------------------
django_bootstrap() {
  step "Django migrate + seed packages + ACL revendeurs"
  local py="${VZONE_ROOT}/backend/.venv/bin/python"
  local manage="${VZONE_ROOT}/backend/manage.py"
  [[ -x "$py" && -f "$manage" ]] || { warn "venv Django introuvable"; return 0; }

  cd "${VZONE_ROOT}/backend"
  run_ok "migrate" "$py" manage.py migrate --noinput
  run_ok "collectstatic" "$py" manage.py collectstatic --noinput

  "$py" manage.py shell <<'PY' || warn "seed packages / ACL"
from apps.packages.services import seed_default_packages
from apps.accounts.models import User, ResellerPrivileges
from apps.accounts.reseller_services import ensure_reseller_privileges

created = seed_default_packages()
print(f"packages créés: {len(created)}")

n = 0
for u in User.objects.filter(role=User.Role.RESELLER):
    if not ResellerPrivileges.objects.filter(user=u).exists():
        can = True
        try:
            can = bool(u.package_assignment.package.can_create_packages)
        except Exception:
            pass
        ensure_reseller_privileges(u, can_create_packages=can)
        n += 1
print(f"ACL revendeurs créées: {n}")
PY
  ok "Django bootstrap"
}

# ---------------------------------------------------------------------------
# Ensure services (nginx, api, homes)
# ---------------------------------------------------------------------------
ensure_core() {
  step "Ensure core (homes, nginx, API, services)"
  mkdir -p "${VZONE_DATA}"/{homes,mail,ssl,acme,repair/jobs,update/jobs,roundcube/sso,phpmyadmin/sso}
  # Ne PAS chown -R tout VZONE_DATA sur vzone:vzone — ça casse le SSO Roundcube
  # (www-data ne peut plus lire /var/lib/vzone/roundcube/sso → path_exists=no).
  chown "${VZONE_USER}:${VZONE_USER}" "${VZONE_DATA}" 2>/dev/null || true
  for d in homes mail ssl acme repair update phpmyadmin; do
    [[ -d "${VZONE_DATA}/${d}" ]] && chown -R "${VZONE_USER}:${VZONE_USER}" "${VZONE_DATA}/${d}" 2>/dev/null || true
  done
  # SSO Roundcube : droits durables (temp/sso sous Roundcube)
  if [[ -f "${SCRIPT_DIR}/ensure-roundcube-sso.sh" ]]; then
    run_ok "ensure-roundcube-sso" bash "${SCRIPT_DIR}/ensure-roundcube-sso.sh"
  fi

  [[ -f "${SCRIPT_DIR}/ensure-homes.sh" ]] && run_ok "ensure-homes" bash "${SCRIPT_DIR}/ensure-homes.sh"
  if [[ -f "${SCRIPT_DIR}/ensure-nginx.sh" ]]; then
    run_ok "ensure-nginx" bash "${SCRIPT_DIR}/ensure-nginx.sh" "${REPO_DIR}/deploy/nginx/vzone.conf"
  fi
  [[ -f "${SCRIPT_DIR}/ensure-vzone-api.sh" ]] && run_ok "ensure-api" bash "${SCRIPT_DIR}/ensure-vzone-api.sh"

  systemctl daemon-reload 2>/dev/null || true
  systemctl enable --now redis-server 2>/dev/null || systemctl enable --now redis 2>/dev/null || true
  systemctl enable --now postgresql 2>/dev/null || true
  systemctl enable nginx vzone-api vzone-worker vzone-beat 2>/dev/null || true
  systemctl restart vzone-api 2>/dev/null || true
  systemctl restart vzone-worker vzone-beat 2>/dev/null || true
  systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Réparations « safe » dès le jour 0 (évite 502 / 404 / mail cassé)
# ---------------------------------------------------------------------------
repair_all_safe() {
  step "Réparations post-install (safe)"

  local repairs=(
    repair-frontend.sh
    repair-api-502.sh
    repair-panel-404.sh
    repair-nginx-500.sh
    repair-domains-403.sh
    repair-external-access.sh
    repair-roundcube.sh
    repair-mail-auth.sh
    repair-smtp.sh
    ensure-roundcube-sso.sh
  )

  local r
  for r in "${repairs[@]}"; do
    if [[ -f "${SCRIPT_DIR}/${r}" ]]; then
      # Ne pas faire échouer tout le bootstrap si une réparation soft échoue
      set +e
      bash "${SCRIPT_DIR}/${r}"
      local rc=$?
      set -e
      if [[ $rc -eq 0 ]]; then
        ok "${r}"
      else
        warn "${r} code=${rc}"
      fi
    fi
  done
}

# ---------------------------------------------------------------------------
# Santé finale
# ---------------------------------------------------------------------------
healthcheck() {
  step "Contrôle santé"
  local admin_port="${VZONE_ADMIN_PORT:-9086}"
  local client_port="${VZONE_CLIENT_PORT:-9082}"
  local webmail_port="${VZONE_WEBMAIL_PORT:-9095}"
  local code

  for port in "$admin_port" "$client_port" "$webmail_port"; do
    code="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "http://127.0.0.1:${port}/" || echo 000)"
    if [[ "$code" =~ ^(200|301|302|303|307|308)$ ]]; then
      ok "port ${port} → HTTP ${code}"
    else
      warn "port ${port} → HTTP ${code} (vérifiez ufw / nginx)"
    fi
  done

  code="$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    "http://127.0.0.1:${admin_port}/api/v1/auth/login/" \
    -H "Content-Type: application/json" -d '{}' || echo 000)"
  if [[ "$code" == "502" || "$code" == "000" ]]; then
    warn "API encore inaccessible (HTTP ${code}) — lancez: bash ${SCRIPT_DIR}/repair-api-502.sh"
  else
    ok "API login → HTTP ${code} (400/401 = normal)"
  fi

  systemctl is-active --quiet vzone-api && ok "vzone-api active" || warn "vzone-api inactive"
  systemctl is-active --quiet nginx && ok "nginx active" || warn "nginx inactive"
}

main() {
  require_root
  load_env
  log "Bootstrap V-zone (root=${VZONE_ROOT})"

  if [[ "$REPAIR_ONLY" != "1" ]]; then
    install_all_modules
    django_bootstrap
  fi
  ensure_core
  repair_all_safe
  # Second passage nginx/api après repairs
  [[ -f "${SCRIPT_DIR}/ensure-nginx.sh" ]] && bash "${SCRIPT_DIR}/ensure-nginx.sh" "${REPO_DIR}/deploy/nginx/vzone.conf" || true
  [[ -f "${SCRIPT_DIR}/ensure-vzone-api.sh" ]] && bash "${SCRIPT_DIR}/ensure-vzone-api.sh" || true
  healthcheck

  echo
  ok "Bootstrap terminé — panel prêt (modules + réparations)."
}

main "$@"
