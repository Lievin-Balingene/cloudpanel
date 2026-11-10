#!/usr/bin/env bash
# AngaPanel — durcissement priorité audit sécurité
#   1) TLS panel (9082/9086) + cookies Secure
#   2) Secrets panel ≠ root SSH
#   3) Couper ubuntu ALL=(ALL) NOPASSWD:ALL
#   4) Restreindre SSH + optionnellement 9086
#
# Usage:
#   sudo bash /opt/vzone-src/scripts/harden-panel-security.sh
#   sudo bash ... --rotate-admin          # régénère le MDP panel (install / incident)
#   VZONE_ADMIN_ALLOW_CIDRS="1.2.3.4/32" sudo bash ...
#   VZONE_SSH_DISABLE_PASSWORD=1 sudo bash ...
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

ROTATE_ADMIN=0
for arg in "$@"; do
  case "$arg" in
    --rotate-admin) ROTATE_ADMIN=1 ;;
  esac
done

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ADMIN_PORT="${VZONE_ADMIN_PORT:-9086}"
CLIENT_PORT="${VZONE_CLIENT_PORT:-9082}"
WEBMAIL_PORT="${VZONE_WEBMAIL_PORT:-9095}"

if [[ -f "$ENV_FILE" ]]; then
  set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a
fi
ADMIN_PORT="${VZONE_ADMIN_PORT:-$ADMIN_PORT}"
CLIENT_PORT="${VZONE_CLIENT_PORT:-$CLIENT_PORT}"
WEBMAIL_PORT="${VZONE_WEBMAIL_PORT:-$WEBMAIL_PORT}"

log() { printf '\033[1;34m[harden]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[harden]\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m[harden]\033[0m %s\n' "$*"; }

mkdir -p /etc/vzone /var/lib/vzone/ssl /var/lib/vzone/acme
REPORT="/etc/vzone/harden-report.txt"
: >"$REPORT"
echo "AngaPanel harden $(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$REPORT"

# ─── 1) TLS panel : activer SSL sur ports dédiés ─────────────────────────────
log "1/5 TLS panel + cookies Secure"
touch "$ENV_FILE"
upsert_env() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >>"$ENV_FILE"
  fi
}
upsert_env "VZONE_PANEL_TLS" "1"
upsert_env "VZONE_FORCE_SECURE_COOKIES" "1"
# Redirect HTTP→HTTPS sur 80/443 seulement ; ports custom sont SSL-only
upsert_env "VZONE_SECURE_SSL_REDIRECT" "0"

# Persiste allowlist WHM (refuse le placeholder VOTRE_IP)
CIDRS_IN="${VZONE_ADMIN_ALLOW_CIDRS:-}"
if [[ -n "$CIDRS_IN" && "$CIDRS_IN" != *"VOTRE_IP"* ]]; then
  upsert_env "VZONE_ADMIN_ALLOW_CIDRS" "$CIDRS_IN"
  ok "Allowlist WHM enregistrée: ${CIDRS_IN}"
elif [[ "$CIDRS_IN" == *"VOTRE_IP"* ]]; then
  warn "Ignorez le placeholder VOTRE_IP — utilisez votre IP publique réelle, ex. 203.0.113.10/32"
fi

if [[ -f "${REPO_DIR}/scripts/ensure-nginx.sh" ]]; then
  bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf" \
    || warn "ensure-nginx a échoué — vérifiez nginx -t"
fi
ok "TLS ports panel demandé (VZONE_PANEL_TLS=1)"
echo "tls=enabled" >>"$REPORT"

# ─── 2) Secrets panel ≠ root (+ Redis requirepass idempotent) ───────────────
log "2/5 Secrets panel / Redis"
if [[ "$ROTATE_ADMIN" -eq 1 ]]; then
  NEW_ADMIN_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 20)"
  if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
    export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-vzone.settings.production}"
    set -a; source "$ENV_FILE"; set +a
    "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<PY
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.filter(username="admin").first() or User.objects.filter(role="administrator").order_by("id").first()
if u:
    u.set_password("${NEW_ADMIN_PASS}")
    u.must_change_password = True
    u.save(update_fields=["password", "must_change_password"])
    print(f"admin_user={u.username}")
else:
    print("admin_user=MISSING")
PY
    cat > /etc/vzone/admin-credentials.txt <<EOF
# Régénéré par harden-panel-security.sh --rotate-admin
# NE PAS réutiliser le mot de passe root SSH
username=admin
temp_password=${NEW_ADMIN_PASS}
must_change_password=true
generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
    chmod 600 /etc/vzone/admin-credentials.txt
    ok "Mot de passe panel admin régénéré → /etc/vzone/admin-credentials.txt"
    echo "panel_admin_password=rotated" >>"$REPORT"
  else
    warn "venv Django absent — rotation admin ignorée"
  fi
else
  ok "Rotation admin ignorée (passez --rotate-admin si besoin)"
  echo "panel_admin_password=unchanged" >>"$REPORT"
fi

# Redis requirepass — une seule fois (si absent)
if command -v redis-cli >/dev/null 2>&1; then
  CONF=""
  for c in /etc/redis/redis.conf /etc/redis.conf; do
    [[ -f "$c" ]] && CONF="$c" && break
  done
  if [[ -n "$CONF" ]] && ! grep -qE '^\s*requirepass\s+\S+' "$CONF"; then
    REDIS_PASS="$(openssl rand -hex 24)"
    echo "requirepass ${REDIS_PASS}" >>"$CONF"
    upsert_env "VZONE_REDIS_URL" "redis://:${REDIS_PASS}@127.0.0.1:6379/0"
    upsert_env "VZONE_CELERY_BROKER_URL" "redis://:${REDIS_PASS}@127.0.0.1:6379/1"
    upsert_env "VZONE_CHANNELS_REDIS_URL" "redis://:${REDIS_PASS}@127.0.0.1:6379/2"
    systemctl restart redis-server 2>/dev/null || systemctl restart redis 2>/dev/null || true
    systemctl restart vzone-api vzone-worker vzone-beat 2>/dev/null || true
    ok "Redis requirepass activé"
    echo "redis=requirepass" >>"$REPORT"
  else
    ok "Redis requirepass déjà présent ou conf absente"
    echo "redis=ok" >>"$REPORT"
  fi
fi

# ─── 3) Couper ubuntu NOPASSWD:ALL ───────────────────────────────────────────
log "3/5 Retrait sudo NOPASSWD pour ubuntu"
REMOVED=0
for f in /etc/sudoers.d/*; do
  [[ -f "$f" ]] || continue
  [[ "$(basename "$f")" == "vzone-panel" ]] && continue
  [[ "$(basename "$f")" == "vzone-terminal" ]] && continue
  if grep -Eq '^[[:space:]]*ubuntu[[:space:]]+ALL=\(ALL(:ALL)?\)[[:space:]]+NOPASSWD:ALL' "$f" 2>/dev/null \
    || grep -Eq '^[[:space:]]*%sudo[[:space:]]+ALL=\(ALL(:ALL)?\)[[:space:]]+NOPASSWD:ALL' "$f" 2>/dev/null; then
    cp -a "$f" "${f}.bak-angapanel-$(date +%Y%m%d%H%M%S)"
    # Remplace NOPASSWD:ALL par ALL (mot de passe requis) pour ubuntu
    sed -i -E \
      -e 's/^([[:space:]]*ubuntu[[:space:]]+ALL=\(ALL(:ALL)?\))[[:space:]]+NOPASSWD:ALL/\1 ALL/' \
      -e 's/^([[:space:]]*%sudo[[:space:]]+ALL=\(ALL(:ALL)?\))[[:space:]]+NOPASSWD:ALL/\1 ALL/' \
      "$f"
    if visudo -cf "$f" >/dev/null 2>&1; then
      ok "Durci $f (NOPASSWD:ALL retiré)"
      REMOVED=1
    else
      warn "sudoers invalide après edit — restauration $f"
      mv -f "${f}.bak-angapanel-"* "$f" 2>/dev/null || true
    fi
  fi
done
# cloud-init classique
if [[ -f /etc/sudoers.d/90-cloud-init-users ]]; then
  if grep -q 'NOPASSWD:ALL' /etc/sudoers.d/90-cloud-init-users; then
    cp -a /etc/sudoers.d/90-cloud-init-users /etc/sudoers.d/90-cloud-init-users.bak-angapanel
    sed -i -E 's/NOPASSWD:ALL/ALL/g' /etc/sudoers.d/90-cloud-init-users
    visudo -cf /etc/sudoers.d/90-cloud-init-users >/dev/null 2>&1 \
      || mv -f /etc/sudoers.d/90-cloud-init-users.bak-angapanel /etc/sudoers.d/90-cloud-init-users
    REMOVED=1
  fi
fi
[[ "$REMOVED" -eq 1 ]] && echo "ubuntu_sudo=password_required" >>"$REPORT" || echo "ubuntu_sudo=unchanged" >>"$REPORT"

# ─── 4) SSH hardening ───────────────────────────────────────────────────────
log "4/5 SSH (PermitRootLogin / PasswordAuthentication)"
SSHD_DROPIN="/etc/ssh/sshd_config.d/99-angapanel-harden.conf"
mkdir -p /etc/ssh/sshd_config.d
cat >"$SSHD_DROPIN" <<'EOF'
# AngaPanel harden-panel-security.sh
PermitRootLogin prohibit-password
PubkeyAuthentication yes
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
X11Forwarding no
MaxAuthTries 4
LoginGraceTime 30
EOF
if [[ "${VZONE_SSH_DISABLE_PASSWORD:-0}" == "1" ]]; then
  echo "PasswordAuthentication no" >>"$SSHD_DROPIN"
  ok "PasswordAuthentication no"
else
  echo "PasswordAuthentication yes" >>"$SSHD_DROPIN"
  warn "PasswordAuthentication encore yes — passez VZONE_SSH_DISABLE_PASSWORD=1 quand les clés SSH sont en place"
fi
if sshd -t 2>/dev/null; then
  systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
  ok "sshd rechargé ($SSHD_DROPIN)"
  echo "ssh=permit_root_prohibit_password" >>"$REPORT"
else
  warn "sshd -t a échoué — drop-in non appliqué"
  rm -f "$SSHD_DROPIN"
fi

# ─── 5) UFW : restreindre 9086 si CIDRS fournis ──────────────────────────────
log "5/5 Pare-feu ports panel"
if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH >/dev/null 2>&1 || ufw allow 22/tcp >/dev/null 2>&1 || true
  ufw allow 80/tcp >/dev/null 2>&1 || true
  ufw allow 443/tcp >/dev/null 2>&1 || true
  ufw allow "${CLIENT_PORT}/tcp" comment "angapanel-client" >/dev/null 2>&1 || ufw allow "${CLIENT_PORT}/tcp" || true
  ufw allow "${WEBMAIL_PORT}/tcp" comment "angapanel-webmail" >/dev/null 2>&1 || true

  CIDRS="${VZONE_ADMIN_ALLOW_CIDRS:-}"
  if [[ -n "$CIDRS" && "$CIDRS" != *"VOTRE_IP"* ]]; then
    # Retire TOUTES les règles 9086 (ouvertes ou anciennes allowlist)
    for _try in $(seq 1 40); do
      NUM="$(ufw status numbered 2>/dev/null | grep -E "${ADMIN_PORT}/tcp" | head -1 | sed -n 's/^\[\s*\([0-9]\+\).*/\1/p')"
      [[ -n "$NUM" ]] || break
      yes | ufw delete "$NUM" >/dev/null 2>&1 || break
    done
    ufw allow from 127.0.0.1 to any port "$ADMIN_PORT" proto tcp comment "angapanel-admin-local" || true
    IFS=',' read -ra LIST <<<"$CIDRS"
    for cidr in "${LIST[@]}"; do
      cidr="$(echo "$cidr" | xargs)"
      [[ -n "$cidr" ]] || continue
      ufw allow from "$cidr" to any port "$ADMIN_PORT" proto tcp comment "angapanel-admin" || true
    done
    ok "UFW :${ADMIN_PORT} restreint à: ${CIDRS} (+ localhost)"
    echo "admin_port=restricted:${CIDRS}" >>"$REPORT"
  else
    ufw allow "${ADMIN_PORT}/tcp" comment "angapanel-admin" >/dev/null 2>&1 || ufw allow "${ADMIN_PORT}/tcp" || true
    warn "9086 encore ouvert au monde — ex: VZONE_ADMIN_ALLOW_CIDRS=203.0.113.10/32 $0"
    echo "admin_port=open_world" >>"$REPORT"
  fi
  ufw --force enable >/dev/null 2>&1 || true
fi

# Recharge nginx pour appliquer allow/deny WHM (même sans CIDRS : portal client sur :80)
if [[ -f "${REPO_DIR}/scripts/ensure-nginx.sh" ]]; then
  bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf" || true
fi

# server_tokens off (nginx version leak)
if [[ -d /etc/nginx ]]; then
  echo "server_tokens off;" >/etc/nginx/conf.d/00-angapanel-hide-version.conf
  nginx -t 2>/dev/null && systemctl reload nginx || true
  echo "nginx_server_tokens=off" >>"$REPORT"
fi

chmod 600 "$REPORT" /etc/vzone/admin-credentials.txt 2>/dev/null || true

echo
ok "Durcissement terminé — rapport: $REPORT"
echo "  • MDP admin panel : sudo cat /etc/vzone/admin-credentials.txt"
echo "  • TLS ports       : VZONE_PANEL_TLS=1 (ensure-nginx)"
echo "  • SSH             : PermitRootLogin prohibit-password"
echo "  • ubuntu sudo     : NOPASSWD:ALL retiré si présent"
echo "  • Restreindre 9086: VZONE_ADMIN_ALLOW_CIDRS=x.x.x.x/32 $0"
