#!/usr/bin/env bash
# Ensure PostgreSQL clusters are online after boot/restart.
set -euo pipefail

if ! command -v pg_lsclusters >/dev/null 2>&1; then
  systemctl start postgresql 2>/dev/null || true
  exit 0
fi

systemctl start postgresql 2>/dev/null || true

lines="$(pg_lsclusters --no-header 2>/dev/null || true)"
if [[ -z "${lines}" ]]; then
  ver="$(ls /usr/lib/postgresql 2>/dev/null | sort -V | awk 'NF{last=$0} END{print last}')"
  if [[ -n "${ver}" ]]; then
    pg_createcluster "${ver}" main --start || true
    lines="$(pg_lsclusters --no-header 2>/dev/null || true)"
  fi
fi

if [[ -n "${lines}" ]]; then
  while read -r ver name _port status _rest; do
    [[ -n "${ver:-}" && -n "${name:-}" ]] || continue
    if [[ "${status}" != "online" ]]; then
      pg_ctlcluster "${ver}" "${name}" start || true
    fi
    systemctl enable "postgresql@${ver}-${name}" 2>/dev/null || true
  done <<< "${lines}"
fi

down="$(pg_lsclusters --no-header 2>/dev/null | awk '$4!="online"{print $0}')"
if [[ -n "${down}" ]]; then
  echo "[vzone] PostgreSQL clusters offline:"
  echo "${down}"
  exit 1
fi
