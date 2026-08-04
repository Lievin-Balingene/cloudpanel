#!/usr/bin/env bash
# Installe/configure PostgreSQL pour le panel + provisionnement live.
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
PG_ADMIN_USER="${VZONE_PG_ADMIN_USER:-vzone}"
PG_ADMIN_DB="${VZONE_PG_ADMIN_DB:-postgres}"
PG_HOST="${VZONE_PG_HOST:-127.0.0.1}"
PG_PORT="${VZONE_PG_PORT:-5432}"

echo "[vzone] Installation PostgreSQL + gestion clusters"

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq postgresql postgresql-contrib postgresql-client
elif command -v dnf >/dev/null 2>&1; then
  dnf -y install postgresql-server postgresql-contrib
  postgresql-setup --initdb 2>/dev/null || true
fi

systemctl daemon-reload
systemctl enable postgresql || true
systemctl start postgresql || true

ensure_clusters() {
  if ! command -v pg_lsclusters >/dev/null 2>&1; then
    return 0
  fi

  local lines
  lines="$(pg_lsclusters --no-header 2>/dev/null || true)"
  if [[ -z "${lines}" ]]; then
    local ver
    ver="$(ls /usr/lib/postgresql 2>/dev/null | sort -V | awk 'NF{last=$0} END{print last}')"
    if [[ -n "${ver}" ]]; then
      echo "[vzone] Création cluster PostgreSQL ${ver}/main"
      pg_createcluster "${ver}" main --start
    fi
    lines="$(pg_lsclusters --no-header 2>/dev/null || true)"
  fi

  if [[ -n "${lines}" ]]; then
    while read -r ver name _port status _rest; do
      [[ -n "${ver:-}" && -n "${name:-}" ]] || continue
      if [[ "${status}" != "online" ]]; then
        echo "[vzone] Démarrage cluster ${ver}/${name}"
        pg_ctlcluster "${ver}" "${name}" start || true
      fi
      systemctl enable "postgresql@${ver}-${name}" 2>/dev/null || true
    done <<< "${lines}"
  fi
}

ensure_clusters
systemctl restart postgresql || true
ensure_clusters

if command -v pg_lsclusters >/dev/null 2>&1; then
  down="$(pg_lsclusters --no-header 2>/dev/null | awk '$4!="online"{print $0}')"
  if [[ -n "${down}" ]]; then
    echo "[vzone] ERREUR: clusters PostgreSQL offline:"
    echo "${down}"
    exit 1
  fi
fi

PG_ADMIN_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a; source "${ENV_FILE}"; set +a
  if [[ -n "${VZONE_PG_ADMIN_PASSWORD:-}" ]]; then
    PG_ADMIN_PASS="${VZONE_PG_ADMIN_PASSWORD}"
  fi
fi

sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${PG_ADMIN_USER}'" | grep -q "1" \
  || sudo -u postgres psql -c "CREATE ROLE ${PG_ADMIN_USER} LOGIN PASSWORD '${PG_ADMIN_PASS}' CREATEDB CREATEROLE;"

sudo -u postgres psql -c "ALTER ROLE ${PG_ADMIN_USER} WITH LOGIN PASSWORD '${PG_ADMIN_PASS}' CREATEDB CREATEROLE;" || true

if [[ -f "${ENV_FILE}" ]]; then
  grep -q '^VZONE_PG_HOST=' "${ENV_FILE}" || echo "VZONE_PG_HOST=${PG_HOST}" >> "${ENV_FILE}"
  grep -q '^VZONE_PG_PORT=' "${ENV_FILE}" || echo "VZONE_PG_PORT=${PG_PORT}" >> "${ENV_FILE}"
  grep -q '^VZONE_PG_ADMIN_USER=' "${ENV_FILE}" || echo "VZONE_PG_ADMIN_USER=${PG_ADMIN_USER}" >> "${ENV_FILE}"
  grep -q '^VZONE_PG_ADMIN_PASSWORD=' "${ENV_FILE}" || echo "VZONE_PG_ADMIN_PASSWORD=${PG_ADMIN_PASS}" >> "${ENV_FILE}"
  grep -q '^VZONE_PG_ADMIN_DB=' "${ENV_FILE}" || echo "VZONE_PG_ADMIN_DB=${PG_ADMIN_DB}" >> "${ENV_FILE}"

  sed -i "s|^VZONE_PG_HOST=.*|VZONE_PG_HOST=${PG_HOST}|" "${ENV_FILE}"
  sed -i "s|^VZONE_PG_PORT=.*|VZONE_PG_PORT=${PG_PORT}|" "${ENV_FILE}"
  sed -i "s|^VZONE_PG_ADMIN_USER=.*|VZONE_PG_ADMIN_USER=${PG_ADMIN_USER}|" "${ENV_FILE}"
  sed -i "s|^VZONE_PG_ADMIN_DB=.*|VZONE_PG_ADMIN_DB=${PG_ADMIN_DB}|" "${ENV_FILE}"
  sed -i "s|^VZONE_DB_PROVISION_MODE=.*|VZONE_DB_PROVISION_MODE=live|" "${ENV_FILE}" 2>/dev/null || true
  grep -q '^VZONE_DB_PROVISION_MODE=' "${ENV_FILE}" || echo "VZONE_DB_PROVISION_MODE=live" >> "${ENV_FILE}"
fi

echo "[vzone] PostgreSQL prêt — admin provisioning: ${PG_ADMIN_USER}@${PG_HOST}:${PG_PORT}"
