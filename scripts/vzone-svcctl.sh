#!/usr/bin/env bash
# Contrôle sécurisé de services système (start|stop|restart|reload|status).
# Allowlist stricte — appelé via sudo -n depuis vzone-api uniquement.
# Usage: vzone-svcctl <action> <unit>
set -euo pipefail

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "root requis" >&2
  exit 1
fi

ACTION="${1:-}"
UNIT="${2:-}"

usage() {
  echo "Usage: vzone-svcctl <start|stop|restart|reload|status> <unit>" >&2
  exit 2
}

[[ -n "$ACTION" && -n "$UNIT" ]] || usage

case "$ACTION" in
  start|stop|restart|reload|status) ;;
  *) usage ;;
esac

# Uniquement des noms d'unités systemd simples (pas de chemins / injections)
if [[ ! "$UNIT" =~ ^[a-zA-Z0-9@._+-]+\.service$ ]] && [[ ! "$UNIT" =~ ^[a-zA-Z0-9@._+-]+$ ]]; then
  echo "unité invalide: ${UNIT}" >&2
  exit 2
fi

# Allowlist (noms sans .service ou avec)
ALLOWED=(
  nginx
  postgresql
  mariadb
  mysql
  mysqld
  redis
  redis-server
  postfix
  dovecot
  opendkim
  fail2ban
  sshd
  ssh
  docker
  named
  bind9
  pure-ftpd
  vsftpd
  proftpd
  vzone-api
  vzone-celery
  vzone-celerybeat
  vzone-beat
  vzone-worker
)

normalize="${UNIT%.service}"
ok=0
for a in "${ALLOWED[@]}"; do
  if [[ "$normalize" == "$a" ]]; then
    ok=1
    break
  fi
done
if [[ "$ok" -ne 1 ]]; then
  echo "unité non autorisée: ${UNIT}" >&2
  exit 3
fi

# Forcer le suffixe .service pour systemctl
TARGET="${normalize}.service"

SYSTEMCTL="$(command -v systemctl || true)"
if [[ -z "$SYSTEMCTL" ]]; then
  for c in /bin/systemctl /usr/bin/systemctl; do
    [[ -x "$c" ]] && SYSTEMCTL="$c" && break
  done
fi
if [[ -z "$SYSTEMCTL" ]]; then
  echo "systemctl introuvable" >&2
  exit 4
fi

# Vérifier que l'unité existe (loaded ou not-found)
if ! "$SYSTEMCTL" cat "$TARGET" >/dev/null 2>&1 \
  && ! "$SYSTEMCTL" list-unit-files "${TARGET}" 2>/dev/null | grep -q "${TARGET}"; then
  # Essayer sans forcer si l'appelant a déjà un template valide
  if ! "$SYSTEMCTL" status "$TARGET" >/dev/null 2>&1 \
    && [[ "$("$SYSTEMCTL" show -p LoadState --value "$TARGET" 2>/dev/null || echo not-found)" == "not-found" ]]; then
    echo "unité introuvable: ${TARGET}" >&2
    exit 5
  fi
fi

case "$ACTION" in
  status)
    "$SYSTEMCTL" is-active "$TARGET" || true
    "$SYSTEMCTL" show "$TARGET" -p ActiveState -p SubState -p UnitFileState --no-pager
    ;;
  *)
    "$SYSTEMCTL" "$ACTION" "$TARGET"
    echo "ok ${ACTION} ${TARGET}"
    "$SYSTEMCTL" is-active "$TARGET" || true
    ;;
esac
