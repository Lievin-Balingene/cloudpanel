#!/usr/bin/env bash
# V-zone Pulse — Resource Governor (cgroups v2 via systemd slices).
# Applique CPU / RAM / Tasks / IOWeight par compte, sans noyau propriétaire.
#
# Usage:
#   vzone-resourcectl apply <user> --cpu-millicores N --memory-mb N --tasks N [--io-weight N]
#   vzone-resourcectl remove <user>
#   vzone-resourcectl status <user>
#   vzone-resourcectl status-all
#   vzone-resourcectl check
set -euo pipefail

HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
CLIENTS_GROUP="${VZONE_CLIENTS_GROUP:-vzone-clients}"
SLICE_DIR="/etc/systemd/system"
STATE_DIR="${VZONE_PULSE_DIR:-/var/lib/vzone/pulse}"
CGROUP_ROOT="${VZONE_CGROUP_ROOT:-/sys/fs/cgroup}"

need_root() {
  [[ ${EUID:-0} -eq 0 ]] || { echo "root requis" >&2; exit 1; }
}

usage() {
  echo "Usage: vzone-resourcectl apply|remove|status|status-all|check ..." >&2
  exit 2
}

slice_name() {
  local u="$1"
  # Nom systemd valide
  echo "vz-pulse-${u}.slice"
}

validate_user() {
  local u="$1"
  [[ "$u" =~ ^[a-z][a-z0-9_-]{1,31}$ ]] || { echo "username invalide" >&2; exit 2; }
  case "$u" in
    root|vzone|nobody|www-data|mysql|postgres) echo "username réservé" >&2; exit 2 ;;
  esac
  id -u "$u" >/dev/null 2>&1 || { echo "compte OS absent: $u" >&2; exit 3; }
}

cpu_quota_pct() {
  # millicores → CPUQuota% (1000 millicores = 100%)
  local mc="$1"
  if [[ "$mc" -le 0 ]]; then
    echo ""
    return
  fi
  # systemd CPUQuota accepte "150%" etc.
  local pct=$(( (mc + 5) / 10 ))
  [[ "$pct" -lt 1 ]] && pct=1
  echo "${pct}%"
}

ensure_dirs() {
  mkdir -p "${STATE_DIR}/meta"
  chmod 755 "${STATE_DIR}"
}

write_slice() {
  local user="$1" cpu_mc="$2" mem_mb="$3" tasks="$4" io_w="$5"
  local slice unit_path drop_dir
  slice="$(slice_name "$user")"
  unit_path="${SLICE_DIR}/${slice}"
  drop_dir="${unit_path}.d"
  mkdir -p "$drop_dir"

  local cpu_line="" mem_line="" tasks_line="" io_line=""
  local cq
  cq="$(cpu_quota_pct "$cpu_mc")"
  if [[ -n "$cq" ]]; then
    cpu_line="CPUQuota=${cq}"
  fi
  if [[ "$mem_mb" -gt 0 ]]; then
    mem_line="MemoryMax=${mem_mb}M"
  fi
  if [[ "$tasks" -gt 0 ]]; then
    tasks_line="TasksMax=${tasks}"
  fi
  if [[ "$io_w" -gt 0 ]]; then
    io_line="IOWeight=${io_w}"
  fi

  cat > "${unit_path}" <<EOF
[Unit]
Description=V-zone Pulse resource slice for ${user}
Documentation=https://github.com/Lievin-Balingene/cloudpanel
Before=slices.target

[Slice]
EOF
  cat > "${drop_dir}/50-limits.conf" <<EOF
[Slice]
${cpu_line}
${mem_line}
${tasks_line}
${io_line}
EOF

  systemctl daemon-reload
  systemctl start "${slice}" 2>/dev/null || true

  ensure_dirs
  cat > "${STATE_DIR}/meta/${user}.json" <<EOF
{"user":"${user}","slice":"${slice}","cpu_millicores":${cpu_mc},"memory_mb":${mem_mb},"tasks":${tasks},"io_weight":${io_w},"updated_at":"$(date -Iseconds)"}
EOF
  chmod 644 "${STATE_DIR}/meta/${user}.json"
}

remove_slice() {
  local user="$1"
  local slice
  slice="$(slice_name "$user")"
  systemctl stop "${slice}" 2>/dev/null || true
  rm -f "${SLICE_DIR}/${slice}"
  rm -rf "${SLICE_DIR}/${slice}.d"
  rm -f "${STATE_DIR}/meta/${user}.json"
  systemctl daemon-reload 2>/dev/null || true
}

read_cgroup_usage() {
  local user="$1"
  local slice path
  slice="$(slice_name "$user")"
  path="${CGROUP_ROOT}/${slice}"
  if [[ ! -d "$path" ]]; then
    # parfois sous system.slice
    path="${CGROUP_ROOT}/system.slice/${slice}"
  fi
  local mem_current=0 mem_max=0 tasks_current=0 cpu_usec=0
  if [[ -d "$path" ]]; then
    [[ -f "${path}/memory.current" ]] && mem_current="$(cat "${path}/memory.current" 2>/dev/null || echo 0)"
    if [[ -f "${path}/memory.max" ]]; then
      mem_max="$(cat "${path}/memory.max" 2>/dev/null || echo max)"
      [[ "$mem_max" == "max" ]] && mem_max=0
    fi
    [[ -f "${path}/pids.current" ]] && tasks_current="$(cat "${path}/pids.current" 2>/dev/null || echo 0)"
    if [[ -f "${path}/cpu.stat" ]]; then
      cpu_usec="$(awk '/^usage_usec/ {print $2}' "${path}/cpu.stat" 2>/dev/null || echo 0)"
    fi
  fi

  local inodes_used=0 disk_bytes=0
  local home="${HOME_ROOT}/${user}"
  if [[ -d "$home" ]]; then
    disk_bytes="$(du -sb "$home" 2>/dev/null | awk '{print $1}' || echo 0)"
    inodes_used="$(find "$home" 2>/dev/null | wc -l | tr -d ' ' || echo 0)"
  fi

  local meta="{}"
  if [[ -f "${STATE_DIR}/meta/${user}.json" ]]; then
    meta="$(cat "${STATE_DIR}/meta/${user}.json")"
  fi

  printf '{"user":"%s","slice":"%s","cgroup_path":"%s","memory_current_bytes":%s,"memory_max_bytes":%s,"tasks_current":%s,"cpu_usage_usec":%s,"disk_bytes":%s,"inodes_used":%s,"limits":%s,"active":%s}\n' \
    "$user" "$slice" "$path" \
    "${mem_current:-0}" "${mem_max:-0}" "${tasks_current:-0}" "${cpu_usec:-0}" \
    "${disk_bytes:-0}" "${inodes_used:-0}" "$meta" \
    "$([[ -d "$path" ]] && echo true || echo false)"
}

cmd_apply() {
  need_root
  local user="${1:-}"
  shift || true
  validate_user "$user"
  local cpu_mc=1000 mem_mb=1024 tasks=100 io_w=100
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --cpu-millicores) cpu_mc="${2:-0}"; shift 2 ;;
      --memory-mb) mem_mb="${2:-0}"; shift 2 ;;
      --tasks) tasks="${2:-0}"; shift 2 ;;
      --io-weight) io_w="${2:-100}"; shift 2 ;;
      *) echo "option inconnue: $1" >&2; exit 2 ;;
    esac
  done
  write_slice "$user" "$cpu_mc" "$mem_mb" "$tasks" "$io_w"
  read_cgroup_usage "$user"
}

cmd_remove() {
  need_root
  local user="${1:-}"
  validate_user "$user"
  remove_slice "$user"
  echo "{\"user\":\"${user}\",\"removed\":true}"
}

cmd_status() {
  local user="${1:-}"
  validate_user "$user"
  read_cgroup_usage "$user"
}

cmd_status_all() {
  ensure_dirs
  echo -n '['
  local first=1 f u
  for f in "${STATE_DIR}/meta"/*.json; do
    [[ -f "$f" ]] || continue
    u="$(basename "$f" .json)"
    if [[ "$first" -eq 1 ]]; then first=0; else echo -n ','; fi
    read_cgroup_usage "$u" | tr -d '\n'
  done
  echo ']'
}

cmd_check() {
  need_root
  command -v systemctl >/dev/null 2>&1 || { echo "systemctl absent" >&2; exit 1; }
  [[ -d "$CGROUP_ROOT" ]] || { echo "cgroup fs absent" >&2; exit 1; }
  exit 0
}

case "${1:-}" in
  apply) shift; cmd_apply "$@" ;;
  remove) shift; cmd_remove "$@" ;;
  status) shift; cmd_status "$@" ;;
  status-all) cmd_status_all ;;
  check) cmd_check ;;
  *) usage ;;
esac
