#!/usr/bin/env bash
# Applique le hostname OS + sync panel (env/nginx/mail). Root uniquement.
set -euo pipefail

HOSTNAME="${1:-}"
APPLY_MAIL="${2:-1}"
PUBLIC_IP="${3:-}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
REPO_ENSURE="${VZONE_ENSURE_NGINX:-/usr/local/sbin/vzone-ensure-nginx}"

if [[ -z "${HOSTNAME}" ]]; then
  echo "Usage: vzone-hostname-set <fqdn> [apply_mail=1] [public_ip]" >&2
  exit 2
fi

HOSTNAME="$(echo "${HOSTNAME}" | tr '[:upper:]' '[:lower:]' | sed 's/\.$//')"

# hostnamectl (systemd)
if command -v hostnamectl >/dev/null 2>&1; then
  hostnamectl set-hostname "${HOSTNAME}"
else
  echo "${HOSTNAME}" > /etc/hostname
  hostname "${HOSTNAME}" || true
fi

# /etc/hosts — garder 127.0.1.1 et IP publique
SHORT="${HOSTNAME%%.*}"
if [[ -n "${PUBLIC_IP}" ]]; then
  if grep -qE "^[[:space:]]*${PUBLIC_IP}[[:space:]]" /etc/hosts; then
    sed -i -E "s|^[[:space:]]*${PUBLIC_IP}[[:space:]].*|${PUBLIC_IP} ${HOSTNAME} ${SHORT}|" /etc/hosts
  else
    echo "${PUBLIC_IP} ${HOSTNAME} ${SHORT}" >> /etc/hosts
  fi
fi
if grep -qE '^[[:space:]]*127\.0\.1\.1[[:space:]]' /etc/hosts; then
  sed -i -E "s|^[[:space:]]*127\.0\.1\.1[[:space:]].*|127.0.1.1 ${HOSTNAME} ${SHORT}|" /etc/hosts
else
  echo "127.0.1.1 ${HOSTNAME} ${SHORT}" >> /etc/hosts
fi

# Panel hostnames + ALLOWED_HOSTS
if [[ -f "${ENV_FILE}" ]]; then
  upsert() {
    local key="$1" value="$2"
    if grep -q "^${key}=" "${ENV_FILE}"; then
      sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
    else
      echo "${key}=${value}" >> "${ENV_FILE}"
    fi
  }

  # Conserve les panel hosts existants, ajoute le nouveau hostname
  CURRENT_PANEL="$(grep '^VZONE_PANEL_HOSTNAMES=' "${ENV_FILE}" | head -n1 | cut -d= -f2- || true)"
  PANEL_LIST="${HOSTNAME}"
  if [[ -n "${CURRENT_PANEL}" ]]; then
    # Remplace le premier host (hostname serveur) en gardant les alias panel
    IFS=',' read -r -a arr <<< "${CURRENT_PANEL}"
    keep=()
    for h in "${arr[@]}"; do
      h="$(echo "$h" | xargs)"
      [[ -z "$h" || "$h" == "${HOSTNAME}" ]] && continue
      keep+=("$h")
    done
    if ((${#keep[@]})); then
      PANEL_LIST="${HOSTNAME},$(IFS=,; echo "${keep[*]}")"
    fi
  fi
  upsert "VZONE_PANEL_HOSTNAMES" "${PANEL_LIST}"

  CURRENT_ALLOWED="$(grep '^VZONE_ALLOWED_HOSTS=' "${ENV_FILE}" | head -n1 | cut -d= -f2- || true)"
  ALLOWED="${HOSTNAME},localhost,127.0.0.1"
  if [[ -n "${PUBLIC_IP}" ]]; then
    ALLOWED="${ALLOWED},${PUBLIC_IP}"
  fi
  if [[ -n "${CURRENT_ALLOWED}" ]]; then
    IFS=',' read -r -a aarr <<< "${CURRENT_ALLOWED}"
    for h in "${aarr[@]}"; do
      h="$(echo "$h" | xargs)"
      [[ -z "$h" ]] && continue
      case ",${ALLOWED}," in
        *",${h},"*) ;;
        *) ALLOWED="${ALLOWED},${h}" ;;
      esac
    done
  fi
  upsert "VZONE_ALLOWED_HOSTS" "${ALLOWED}"
fi

# Postfix myhostname
if [[ "${APPLY_MAIL}" == "1" ]] && command -v postconf >/dev/null 2>&1; then
  postconf -e "myhostname = ${HOSTNAME}" || true
  systemctl reload postfix 2>/dev/null || systemctl restart postfix 2>/dev/null || true
fi

# Régénérer nginx panel
if [[ -x "${REPO_ENSURE}" ]]; then
  "${REPO_ENSURE}" || true
elif [[ -f /opt/vzone-src/scripts/ensure-nginx.sh ]]; then
  bash /opt/vzone-src/scripts/ensure-nginx.sh /opt/vzone/deploy/nginx/vzone.conf || true
elif [[ -f /opt/vzone/scripts/ensure-nginx.sh ]]; then
  bash /opt/vzone/scripts/ensure-nginx.sh /opt/vzone/deploy/nginx/vzone.conf || true
fi

# Note: ne pas restart vzone-api ici (la requête WHM attend encore le .result).
# L'agent redémarre l'API après avoir écrit le résultat.

echo "{\"ok\":true,\"hostname\":\"${HOSTNAME}\"}"
