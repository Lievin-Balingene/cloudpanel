#!/usr/bin/env bash
# Lecture sécurisée des journaux web (nginx / OLS) pour l'API vzone.
# Usage: vzone-read-web-log --bytes <N> -- <absolute-path>
#        vzone-read-web-log --stat -- <absolute-path>
set -euo pipefail

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "root requis" >&2
  exit 1
fi

MODE="bytes"
BYTES=524288
PATH_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bytes)
      BYTES="${2:-}"
      shift 2
      ;;
    --stat)
      MODE="stat"
      shift
      ;;
    --)
      shift
      PATH_ARG="${1:-}"
      shift || true
      break
      ;;
    *)
      PATH_ARG="$1"
      shift
      break
      ;;
  esac
done

if [[ -z "$PATH_ARG" ]]; then
  echo "Usage: vzone-read-web-log [--stat|--bytes N] -- /var/log/nginx/<file>" >&2
  exit 2
fi

if [[ ! "$BYTES" =~ ^[0-9]+$ ]] || (( BYTES < 1024 || BYTES > 2097152 )); then
  echo "bytes invalide (1KiB–2MiB)" >&2
  exit 2
fi

# Pas de chemins relatifs / traversal dans l'argument brut
if [[ "$PATH_ARG" != /* ]] || [[ "$PATH_ARG" == *..* ]]; then
  echo "chemin interdit" >&2
  exit 2
fi

RESOLVED="$(readlink -f -- "$PATH_ARG" 2>/dev/null || realpath -- "$PATH_ARG" 2>/dev/null || true)"
if [[ -z "$RESOLVED" ]]; then
  # Fichier absent : empty pour --stat / --bytes
  if [[ "$MODE" == "stat" ]]; then
    printf 'exists=0\nsize=0\nmtime=0\npath=%s\n' "$PATH_ARG"
    exit 0
  fi
  exit 0
fi

case "$RESOLVED" in
  /var/log/nginx/*) ;;
  /var/lib/vzone/ols/logs/*) ;;
  *)
    echo "hors zone autorisée: $RESOLVED" >&2
    exit 2
    ;;
esac

if [[ ! -f "$RESOLVED" ]]; then
  if [[ "$MODE" == "stat" ]]; then
    printf 'exists=0\nsize=0\nmtime=0\npath=%s\n' "$RESOLVED"
    exit 0
  fi
  exit 0
fi

if [[ "$MODE" == "stat" ]]; then
  SIZE="$(stat -c '%s' -- "$RESOLVED" 2>/dev/null || echo 0)"
  MTIME="$(stat -c '%Y' -- "$RESOLVED" 2>/dev/null || echo 0)"
  printf 'exists=1\nsize=%s\nmtime=%s\npath=%s\n' "$SIZE" "$MTIME" "$RESOLVED"
  exit 0
fi

# Queue du fichier (équivalent seek fin - bytes)
tail -c "$BYTES" -- "$RESOLVED"
