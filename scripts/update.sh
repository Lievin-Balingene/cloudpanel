#!/usr/bin/env bash
# Mise à jour de V-zone Panel
set -euo pipefail

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }
[[ -d "$VZONE_ROOT" ]] || { echo "Installation introuvable: $VZONE_ROOT"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${REPO_DIR}/VERSION")"

echo "[vzone] Mise à jour vers ${VERSION}"
# Ne pas couper l'API pendant tout le build frontend (sinon login = 502).
# Court stop uniquement autour des migrations (voir plus bas).

# Ne jamais supprimer frontend/dist via --delete : il n'est pas dans le dépôt git.
# Sinon un échec migrate/pip laisse le panel en 404 (index.html absent).
rsync -a --delete \
  --exclude '.git' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude 'backend/.venv' \
  --exclude '.env' \
  --exclude '.data' \
  --exclude '.logs' \
  "${REPO_DIR}/" "${VZONE_ROOT}/"

BACKEND_OK=1
# shellcheck disable=SC1091
source "${VZONE_ROOT}/backend/.venv/bin/activate"
set -a; source /etc/vzone/vzone.env; set +a
export DJANGO_SETTINGS_MODULE=vzone.settings.production
pip install -r "${VZONE_ROOT}/backend/requirements/prod.txt" || BACKEND_OK=0
cd "${VZONE_ROOT}/backend"
# Court redémarrage API uniquement pour appliquer le nouveau code + migrations
systemctl stop vzone-api vzone-worker vzone-beat 2>/dev/null || true
python manage.py migrate --noinput || BACKEND_OK=0
python manage.py collectstatic --noinput || true
deactivate
systemctl start vzone-api vzone-worker vzone-beat 2>/dev/null || true

# Frontend : toujours reconstruire (évite 404 nginx sur toutes les pages)
cd "${VZONE_ROOT}/frontend"
npm ci || npm install
npm run build
if [[ ! -f "${VZONE_ROOT}/frontend/dist/index.html" ]]; then
  echo "[vzone] ERREUR: build frontend échoué — ${VZONE_ROOT}/frontend/dist/index.html manquant" >&2
  echo "[vzone] Réparez avec: sudo bash ${REPO_DIR}/scripts/repair-frontend.sh" >&2
  exit 1
fi
chmod -R a+rX "${VZONE_ROOT}/frontend/dist" || true

if [[ "${BACKEND_OK}" -ne 1 ]]; then
  echo "[vzone] ERREUR: étapes backend (pip/migrate) ont échoué — corrigez puis relancez update.sh" >&2
  exit 1
fi

# (Ré)installe les unités systemd — utile après une install partielle
install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-api.service" /etc/systemd/system/
install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-worker.service" /etc/systemd/system/
install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-beat.service" /etc/systemd/system/
# Droits .env : lisible par l'utilisateur système vzone (commandes manage.py)
if [[ -f /etc/vzone/vzone.env ]]; then
  chown root:vzone /etc/vzone/vzone.env
  chmod 640 /etc/vzone/vzone.env
fi

bash "${REPO_DIR}/scripts/ensure-homes.sh"
# Recharger env après migration éventuelle de VZONE_HOME_ROOT
set -a; source /etc/vzone/vzone.env; set +a

# Recrée les homes manquants pour tous les comptes (idempotent)
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" shell <<'PY' || true
from apps.accounts.models import User
from apps.accounts.services import provision_account_home
for u in User.objects.all():
    try:
        provision_account_home(u)
    except Exception as exc:
        print(u.username, exc)
PY
fi

# Stack mail Postfix/Dovecot/OpenDKIM (idempotent)
if [[ -f "${REPO_DIR}/scripts/install-mail.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-mail.sh" || echo "[vzone] Avertissement: install-mail.sh a échoué"
fi
# DKIM / SPF / tables OpenDKIM (clés+DNS ; milters OFF — SMTP prioritaire)
if [[ -f "${REPO_DIR}/scripts/repair-mail-reputation.sh" ]]; then
  bash "${REPO_DIR}/scripts/repair-mail-reputation.sh" || echo "[vzone] Avertissement: repair-mail-reputation.sh a échoué"
fi
# Ceinture: SMTP sans milters après chaque update
if [[ -f "${REPO_DIR}/scripts/repair-smtp.sh" ]]; then
  bash "${REPO_DIR}/scripts/repair-smtp.sh" || echo "[vzone] Avertissement: repair-smtp.sh a échoué"
fi

# phpMyAdmin + MariaDB + PHP-FPM
if [[ -f "${REPO_DIR}/scripts/install-phpmyadmin.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-phpmyadmin.sh" || echo "[vzone] Avertissement: install-phpmyadmin.sh a échoué"
fi

# PostgreSQL clusters + provisioning live
if [[ -f "${REPO_DIR}/scripts/install-postgresql.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-postgresql.sh" || echo "[vzone] Avertissement: install-postgresql.sh a échoué"
fi

# Roundcube Webmail
if [[ -f "${REPO_DIR}/scripts/install-roundcube.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-roundcube.sh" || echo "[vzone] Avertissement: install-roundcube.sh a échoué"
fi

# Certbot / Let's Encrypt
if [[ -f "${REPO_DIR}/scripts/install-certbot.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-certbot.sh" || echo "[vzone] Avertissement: install-certbot.sh a échoué"
fi

# DNS autoritaire (BIND9) — zones panel → Internet
if [[ -f "${REPO_DIR}/scripts/ensure-dns.sh" ]]; then
  bash "${REPO_DIR}/scripts/ensure-dns.sh" || echo "[vzone] Avertissement: ensure-dns.sh a échoué"
fi

# Agent hostname WHM (Basic Setup)
if [[ -f "${REPO_DIR}/scripts/install-hostname-agent.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-hostname-agent.sh" || echo "[vzone] Avertissement: install-hostname-agent.sh a échoué"
fi

# Agent mise à jour panel (WHM → git pull + update.sh)
if [[ -f "${REPO_DIR}/scripts/install-update-agent.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-update-agent.sh" || echo "[vzone] Avertissement: install-update-agent.sh a échoué"
fi

# Agent réparations WHM (scripts repair-* allowlistés)
if [[ -f "${REPO_DIR}/scripts/install-repair-agent.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-repair-agent.sh" || echo "[vzone] Avertissement: install-repair-agent.sh a échoué"
fi

# Sudoers terminal (drop privileges → comptes vzone-clients)
if [[ -f "${REPO_DIR}/scripts/ensure-terminal-sudoers.sh" ]]; then
  bash "${REPO_DIR}/scripts/ensure-terminal-sudoers.sh" || echo "[vzone] Avertissement: ensure-terminal-sudoers.sh a échoué"
fi

# Helper root création /home/<user> (évite Permission denied Errno 13)
if [[ -f "${REPO_DIR}/scripts/ensure-mkhome-sudoers.sh" ]]; then
  bash "${REPO_DIR}/scripts/ensure-mkhome-sudoers.sh" || echo "[vzone] Avertissement: ensure-mkhome-sudoers.sh a échoué"
fi

# Secret FTP interne si manquant (fail-closed sinon)
if [[ -f /etc/vzone/vzone.env ]] && ! grep -q '^VZONE_FTP_AUTH_SECRET=.\+' /etc/vzone/vzone.env 2>/dev/null; then
  FTP_SECRET="$(openssl rand -hex 32)"
  if grep -q '^VZONE_FTP_AUTH_SECRET=' /etc/vzone/vzone.env; then
    sed -i "s|^VZONE_FTP_AUTH_SECRET=.*|VZONE_FTP_AUTH_SECRET=${FTP_SECRET}|" /etc/vzone/vzone.env
  else
    echo "VZONE_FTP_AUTH_SECRET=${FTP_SECRET}" >> /etc/vzone/vzone.env
  fi
  echo "[vzone] VZONE_FTP_AUTH_SECRET généré"
fi

# OpenLiteSpeed (opt-in / auto — si installé ou flag)
OLS_FLAG="${VZONE_OLS_ENABLED:-auto}"
if [[ -f /etc/vzone/vzone.env ]]; then
  # shellcheck disable=SC1091
  OLS_FLAG="$(grep -E '^VZONE_OLS_ENABLED=' /etc/vzone/vzone.env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '[:space:]' || echo "${OLS_FLAG}")"
fi
if [[ -f /var/lib/vzone/ols/.installed ]] || [[ "${OLS_FLAG}" =~ ^(1|true|TRUE|yes|YES|auto|AUTO)$ ]]; then
  if [[ -f "${REPO_DIR}/scripts/install-openlitespeed.sh" ]]; then
    bash "${REPO_DIR}/scripts/install-openlitespeed.sh" || echo "[vzone] Avertissement: install-openlitespeed.sh a échoué"
  fi
fi

# WP-CLI / WordPress
if [[ -f "${REPO_DIR}/scripts/install-wp-cli.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-wp-cli.sh" || echo "[vzone] Avertissement: install-wp-cli.sh a échoué"
fi

# Kubernetes / kubectl
if [[ -f "${REPO_DIR}/scripts/install-kubernetes.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-kubernetes.sh" || echo "[vzone] Avertissement: install-kubernetes.sh a échoué"
fi

install -m 755 "${REPO_DIR}/scripts/vzone-postgresql-ensure.sh" /usr/local/sbin/vzone-postgresql-ensure
install -m 644 "${VZONE_ROOT}/deploy/systemd/vzone-postgresql.service" /etc/systemd/system/vzone-postgresql.service

bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf"

# Appliquer vhosts SSL + ouvrir 443 + reload
if [[ -f "${REPO_DIR}/scripts/ensure-https.sh" ]]; then
  bash "${REPO_DIR}/scripts/ensure-https.sh" || echo "[vzone] Avertissement: ensure-https.sh a échoué"
fi

# Vérifier que le default_server panel est bien actif
if ! nginx -T 2>/dev/null | grep -q 'zz-vzone-panel.conf\|frontend/dist'; then
  echo "[vzone] ALERTE: conf panel absente de nginx -T — lancez scripts/repair-panel-404.sh"
fi

systemctl daemon-reload
systemctl enable --now redis-server 2>/dev/null || systemctl enable --now redis 2>/dev/null || true
systemctl enable --now vzone-postgresql.service 2>/dev/null || true
systemctl enable --now vzone-api vzone-worker vzone-beat nginx

# Garantir que le login ne tombe pas en 502 après update
if ! ss -lntp 2>/dev/null | grep -q ':8000'; then
  echo "[vzone] API absente sur :8000 — repair-api-502"
  bash "${REPO_DIR}/scripts/repair-api-502.sh" || true
else
  systemctl restart vzone-api
  sleep 2
fi

# Cron Jobs (agent root → /etc/cron.d)
if [[ -f "${REPO_DIR}/scripts/install-cron.sh" ]]; then
  bash "${REPO_DIR}/scripts/install-cron.sh" || echo "[vzone] Avertissement: install-cron.sh a échoué"
fi

# Apps Python : relancer les process morts (502 nginx → port app)
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  echo "[vzone] Réconciliation apps Python…"
  (
    set -a
    # shellcheck disable=SC1091
    source /etc/vzone/vzone.env 2>/dev/null || true
    set +a
    export DJANGO_SETTINGS_MODULE=vzone.settings.production
    cd "${VZONE_ROOT}/backend"
    .venv/bin/python manage.py reconcile_python_apps
  ) || echo "[vzone] Avertissement: reconcile_python_apps a échoué"
fi

echo "[vzone] Mise à jour terminée — version ${VERSION}"
echo "[vzone] Services : $(systemctl is-active vzone-api vzone-worker vzone-beat nginx | tr '\n' ' ')"
ss -lntp 2>/dev/null | grep ':8000' || echo "[vzone] ALERTE: pas d'écoute :8000"
