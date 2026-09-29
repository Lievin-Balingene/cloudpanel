#!/usr/bin/env bash
# Donne à l'utilisateur API (vzone) l'accès au socket Docker.
# Cause fréquente de « Échec commande Docker » : permission denied sur docker.sock.
# Usage: sudo bash scripts/ensure-docker-access.sh
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis" >&2; exit 1; }

VZONE_USER="${VZONE_USER:-vzone}"

log() { printf '[vzone-docker] %s\n' "$*"; }

if ! command -v docker >/dev/null 2>&1; then
  log "Docker absent — installation via get.docker.com…"
  curl -fsSL https://get.docker.com | sh
fi

systemctl enable docker 2>/dev/null || true
systemctl start docker 2>/dev/null || true

# Plage ports publiés (host→container) — accès public style cPanel
DOCKER_PORT_START="${VZONE_DOCKER_PORT_START:-12000}"
DOCKER_PORT_END="${VZONE_DOCKER_PORT_END:-18999}"
if command -v ufw >/dev/null 2>&1; then
  ufw allow "${DOCKER_PORT_START}:${DOCKER_PORT_END}/tcp" comment "vzone-docker" 2>/dev/null \
    || ufw allow "${DOCKER_PORT_START}:${DOCKER_PORT_END}/tcp" || true
  log "UFW: TCP ${DOCKER_PORT_START}-${DOCKER_PORT_END} autorisé"
fi
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
  firewall-cmd --permanent --add-port="${DOCKER_PORT_START}-${DOCKER_PORT_END}/tcp" 2>/dev/null || true
  firewall-cmd --reload 2>/dev/null || true
  log "firewalld: TCP ${DOCKER_PORT_START}-${DOCKER_PORT_END} autorisé"
fi

if ! getent group docker >/dev/null 2>&1; then
  groupadd --system docker
  log "Groupe docker créé"
fi

if id "$VZONE_USER" >/dev/null 2>&1; then
  usermod -aG docker "$VZONE_USER"
  log "Utilisateur ${VZONE_USER} ajouté au groupe docker"
else
  log "Avertissement: utilisateur ${VZONE_USER} introuvable"
fi

# Drop-in systemd : SupplementaryGroups=docker (fiable même sans nouvelle session)
mkdir -p /etc/systemd/system/vzone-api.service.d
cat > /etc/systemd/system/vzone-api.service.d/docker.conf <<'EOF'
[Service]
SupplementaryGroups=docker
EOF

# Worker peut aussi lancer des jobs docker
if [[ -f /etc/systemd/system/vzone-worker.service ]]; then
  mkdir -p /etc/systemd/system/vzone-worker.service.d
  cat > /etc/systemd/system/vzone-worker.service.d/docker.conf <<'EOF'
[Service]
SupplementaryGroups=docker
EOF
fi

systemctl daemon-reload
systemctl restart docker 2>/dev/null || true
systemctl restart vzone-api 2>/dev/null || true
systemctl restart vzone-worker 2>/dev/null || true

sleep 1
if sudo -u "$VZONE_USER" docker info >/dev/null 2>&1; then
  log "OK — ${VZONE_USER} peut parler au démon Docker"
  exit 0
fi

# Fallback : test via le socket (groupe pas encore effectif sans restart complet)
if docker info >/dev/null 2>&1; then
  log "Docker OK en root. Si l'API échoue encore, redémarrez : systemctl restart vzone-api"
  exit 0
fi

log "ERREUR: docker info échoue encore" >&2
docker info 2>&1 | head -n 20 >&2 || true
exit 1
