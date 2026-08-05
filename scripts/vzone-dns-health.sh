#!/usr/bin/env bash
# Santé DNS V-zone : détecte SERVFAIL / zones cassées et republie automatiquement.
# Installé comme timer systemd (toutes les 5 min) via ensure-dns.sh.
set -euo pipefail

LOG_DIR="${VZONE_LOG:-/var/log/vzone}"
mkdir -p "${LOG_DIR}"
LOG="${LOG_DIR}/dns-health.log"
exec >>"${LOG}" 2>&1

echo "=== $(date -Is) vzone-dns-health ==="

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
NAMED_DIR="${VZONE_DNS_DIR:-/var/lib/vzone/named}"
ZONES_DIR="${NAMED_DIR}/zones"
ENV_FILE="${VZONE_ENV:-/etc/vzone/vzone.env}"

need_resync=0

# 1) Fichiers zone : named-checkzone + garde TXT
if [[ -d "${ZONES_DIR}" ]] && command -v named-checkzone >/dev/null 2>&1; then
  shopt -s nullglob
  for zf in "${ZONES_DIR}"/*.zone; do
    zname="$(basename "${zf}" .zone)"
    if ! named-checkzone "${zname}" "${zf}" >/dev/null 2>&1; then
      echo "[health] FAIL named-checkzone ${zname}"
      need_resync=1
    fi
  done
  shopt -u nullglob
fi

# 2) Réponses locales : SERVFAIL = zone cassée chargée
if command -v dig >/dev/null 2>&1 && [[ -d "${ZONES_DIR}" ]]; then
  shopt -s nullglob
  for zf in "${ZONES_DIR}"/*.zone; do
    zname="$(basename "${zf}" .zone)"
    status="$(dig @127.0.0.1 "${zname}" SOA +time=1 +tries=1 +norecurse 2>/dev/null \
      | awk '/status:/{print $6}' | tr -d ',' || true)"
    if [[ "${status}" == "SERVFAIL" ]]; then
      echo "[health] SERVFAIL local pour ${zname}"
      need_resync=1
    elif [[ -z "${status}" ]]; then
      # dig timeout / named down
      if ! ss -ulnp 2>/dev/null | grep -qE ':53\s'; then
        echo "[health] named n'écoute pas sur :53"
        need_resync=1
        break
      fi
    fi
  done
  shopt -u nullglob
fi

if [[ "${need_resync}" -eq 0 ]]; then
  echo "[health] OK"
  exit 0
fi

echo "[health] Republie les zones (sync_dns_zones)…"
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" && -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  export VZONE_DNS_ZONES_DIR="${ZONES_DIR}"
  export VZONE_DNS_ZONES_CONF="${NAMED_DIR}/zones.conf"
  export VZONE_DNS_RELOAD_FLAG="${NAMED_DIR}/reload.requested"
  "${VZONE_ROOT}/backend/.venv/bin/python" \
    "${VZONE_ROOT}/backend/manage.py" sync_dns_zones || echo "[health] sync_dns_zones a échoué"
  "${VZONE_ROOT}/backend/.venv/bin/python" \
    "${VZONE_ROOT}/backend/manage.py" check_dns_zones --disk-files || echo "[health] check_dns_zones a échoué"
fi

systemctl restart named 2>/dev/null || systemctl restart bind9 2>/dev/null || true
sleep 1

# Re-test rapide
if command -v dig >/dev/null 2>&1 && [[ -d "${ZONES_DIR}" ]]; then
  shopt -s nullglob
  still_bad=0
  for zf in "${ZONES_DIR}"/*.zone; do
    zname="$(basename "${zf}" .zone)"
    status="$(dig @127.0.0.1 "${zname}" SOA +time=1 +tries=1 +norecurse 2>/dev/null \
      | awk '/status:/{print $6}' | tr -d ',' || true)"
    if [[ "${status}" == "SERVFAIL" ]]; then
      echo "[health] TOUJOURS SERVFAIL: ${zname}"
      still_bad=1
    else
      echo "[health] recovered ${zname} status=${status:-unknown}"
    fi
  done
  shopt -u nullglob
  if [[ "${still_bad}" -eq 1 ]]; then
    echo "[health] ALERTE: SERVFAIL persistant — voir journalctl -u named"
    exit 1
  fi
fi

echo "[health] recovery done"
exit 0
