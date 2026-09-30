#!/usr/bin/env bash
# Tue le(s) process qui écoutent sur un port TCP local (gunicorn orphelin).
# Usage: vzone-kill-port <port>
# Appelé via sudo -n depuis vzone-api uniquement.
set -euo pipefail

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "root requis" >&2
  exit 1
fi

PORT="${1:-}"
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then
  echo "Usage: vzone-kill-port <port>  (1024-65535)" >&2
  exit 2
fi

# Plage apps Python/Node V-zone (évite de tuer des services système bas)
if (( PORT < 8000 || PORT > 29999 )); then
  echo "port hors plage apps V-zone (8000-29999): ${PORT}" >&2
  exit 2
fi

kill_pid() {
  local pid="$1"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  # Ne jamais tuer PID 1 / kernel threads
  (( pid <= 1 )) && return 0
  kill -TERM "$pid" 2>/dev/null || true
  sleep 0.25
  if kill -0 "$pid" 2>/dev/null; then
    # groupe process si leader
    kill -TERM "-$pid" 2>/dev/null || true
    sleep 0.25
  fi
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" 2>/dev/null || true
    kill -KILL "-$pid" 2>/dev/null || true
  fi
}

collect_pids() {
  local p
  # ss (iproute2)
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :${PORT}" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 || true
  fi
  # lsof
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true
  fi
  # fuser
  if command -v fuser >/dev/null 2>&1; then
    fuser "${PORT}/tcp" 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' || true
  fi
}

mapfile -t PIDS < <(collect_pids | sort -u)
if ((${#PIDS[@]} == 0)); then
  # Dernier filet : fuser -k
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
  fi
  echo "port ${PORT}: aucun listener (ou déjà libre)"
  exit 0
fi

echo "port ${PORT}: kill PIDs ${PIDS[*]}"
for p in "${PIDS[@]}"; do
  kill_pid "$p"
done

# Filet fuser
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
fi

# Attendre libération
for _ in 1 2 3 4 5 6 7 8 9 10; do
  left="$(collect_pids | sort -u | tr '\n' ' ')"
  [[ -z "${left// }" ]] && break
  sleep 0.2
done

left="$(collect_pids | sort -u | tr '\n' ' ')"
if [[ -n "${left// }" ]]; then
  echo "AVERTISSEMENT: port ${PORT} encore occupé par: ${left}" >&2
  exit 1
fi

echo "port ${PORT}: libre"
exit 0
