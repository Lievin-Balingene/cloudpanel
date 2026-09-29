#!/usr/bin/env bash
# SMTP Restrictions (style cPanel WHM) — empêche les comptes de by-passer le MTA.
# Seuls root, le MTA (postfix/exim) et mailman peuvent ouvrir des connexions
# TCP sortantes vers le port 25 distant.
#
# Usage:
#   vzone-smtp-restrictions --status
#   vzone-smtp-restrictions --enable
#   vzone-smtp-restrictions --disable
#   vzone-smtp-restrictions --check
set -euo pipefail

STATE_DIR="${VZONE_SMTP_RESTRICT_DIR:-/var/lib/vzone/smtp-restrictions}"
STATE_FILE="${STATE_DIR}/enabled"
CHAIN="VZONE_SMTP"
COMMENT="vzone-smtp-restrict"
IPTABLES_BIN="${VZONE_IPTABLES_BIN:-$(command -v iptables || true)}"
IP6TABLES_BIN="${VZONE_IP6TABLES_BIN:-$(command -v ip6tables || true)}"

# UIDs autorisés à joindre des SMTP distants (port 25)
ALLOW_USERS=(root postfix mail mailnull Debian-exim exim mailman)

usage() {
  echo "Usage: vzone-smtp-restrictions --status|--enable|--disable|--check" >&2
  exit 2
}

need_root() {
  if [[ ${EUID:-0} -ne 0 ]]; then
    echo "root requis (sudoers vzone-panel)" >&2
    exit 1
  fi
}

ensure_state_dir() {
  mkdir -p "${STATE_DIR}"
  chmod 755 "${STATE_DIR}"
}

write_state() {
  ensure_state_dir
  echo "$1" > "${STATE_FILE}"
  chmod 644 "${STATE_FILE}"
}

read_state_file() {
  if [[ -f "${STATE_FILE}" ]]; then
    tr -d '[:space:]' < "${STATE_FILE}"
  else
    echo "0"
  fi
}

chain_exists() {
  local bin="$1"
  [[ -n "$bin" && -x "$bin" ]] || return 1
  "$bin" -nL "${CHAIN}" >/dev/null 2>&1
}

jump_exists() {
  local bin="$1"
  [[ -n "$bin" && -x "$bin" ]] || return 1
  "$bin" -C OUTPUT -p tcp --dport 25 -j "${CHAIN}" >/dev/null 2>&1
}

flush_family() {
  local bin="$1"
  [[ -n "$bin" && -x "$bin" ]] || return 0
  if jump_exists "$bin"; then
    "$bin" -D OUTPUT -p tcp --dport 25 -j "${CHAIN}" 2>/dev/null || true
  fi
  if chain_exists "$bin"; then
    "$bin" -F "${CHAIN}" 2>/dev/null || true
    "$bin" -X "${CHAIN}" 2>/dev/null || true
  fi
}

apply_family() {
  local bin="$1"
  local loop_cidr="$2"
  [[ -n "$bin" && -x "$bin" ]] || return 0

  # Remplace proprement la chaîne
  if jump_exists "$bin"; then
    "$bin" -D OUTPUT -p tcp --dport 25 -j "${CHAIN}" 2>/dev/null || true
  fi
  if chain_exists "$bin"; then
    "$bin" -F "${CHAIN}" 2>/dev/null || true
  else
    "$bin" -N "${CHAIN}"
  fi

  # Loopback / local MTA
  "$bin" -A "${CHAIN}" -o lo -m comment --comment "${COMMENT}" -j RETURN
  "$bin" -A "${CHAIN}" -d "${loop_cidr}" -m comment --comment "${COMMENT}" -j RETURN

  local user
  for user in "${ALLOW_USERS[@]}"; do
    if id -u "$user" >/dev/null 2>&1; then
      "$bin" -A "${CHAIN}" -m owner --uid-owner "$user" \
        -m comment --comment "${COMMENT}" -j RETURN 2>/dev/null \
        || "$bin" -A "${CHAIN}" -m owner --uid-owner "$(id -u "$user")" \
             -m comment --comment "${COMMENT}" -j RETURN
    fi
  done

  "$bin" -A "${CHAIN}" -m comment --comment "${COMMENT}" \
    -j REJECT --reject-with icmp-port-unreachable 2>/dev/null \
    || "$bin" -A "${CHAIN}" -m comment --comment "${COMMENT}" -j REJECT

  "$bin" -I OUTPUT -p tcp --dport 25 -j "${CHAIN}"
}

live_enabled() {
  if [[ -n "${IPTABLES_BIN}" && -x "${IPTABLES_BIN}" ]]; then
    jump_exists "${IPTABLES_BIN}" && return 0
  fi
  return 1
}

cmd_status() {
  ensure_state_dir
  local file_state live
  file_state="$(read_state_file)"
  if live_enabled; then
    live="1"
  else
    live="0"
  fi
  # Préférer l'état réel iptables si disponible
  local enabled="$live"
  if [[ -z "${IPTABLES_BIN}" || ! -x "${IPTABLES_BIN}" ]]; then
    enabled="$file_state"
  fi
  local allowed=()
  local user
  for user in "${ALLOW_USERS[@]}"; do
    if id -u "$user" >/dev/null 2>&1; then
      allowed+=("$user")
    fi
  done
  printf '{"enabled":%s,"state_file":%s,"iptables_live":%s,"allowed_users":[%s],"ports":[25],"helper":"vzone-smtp-restrictions"}\n' \
    "$([[ "$enabled" == "1" ]] && echo true || echo false)" \
    "$([[ "$file_state" == "1" ]] && echo true || echo false)" \
    "$([[ "$live" == "1" ]] && echo true || echo false)" \
    "$(printf '"%s",' "${allowed[@]:-}" | sed 's/,$//')"
}

cmd_enable() {
  need_root
  ensure_state_dir
  if [[ -z "${IPTABLES_BIN}" || ! -x "${IPTABLES_BIN}" ]]; then
    write_state 1
    echo '{"enabled":true,"mock":true,"detail":"iptables absent — état enregistré (mock)"}'
    return 0
  fi
  apply_family "${IPTABLES_BIN}" "127.0.0.1/8"
  if [[ -n "${IP6TABLES_BIN}" && -x "${IP6TABLES_BIN}" ]]; then
    apply_family "${IP6TABLES_BIN}" "::1/128" || true
  fi
  write_state 1
  echo '{"enabled":true,"mock":false,"detail":"SMTP restrictions actives (OUTPUT tcp/25)"}'
}

cmd_disable() {
  need_root
  ensure_state_dir
  flush_family "${IPTABLES_BIN:-}"
  flush_family "${IP6TABLES_BIN:-}"
  write_state 0
  echo '{"enabled":false,"mock":false,"detail":"SMTP restrictions désactivées"}'
}

cmd_check() {
  need_root
  # Smoke : le binaire répond
  exit 0
}

case "${1:-}" in
  --status) cmd_status ;;
  --enable) cmd_enable ;;
  --disable) cmd_disable ;;
  --check) cmd_check ;;
  *) usage ;;
esac
