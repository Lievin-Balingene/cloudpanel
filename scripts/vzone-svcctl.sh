#!/usr/bin/env bash
# Contrôle sécurisé de services système (start|stop|restart|reload|status).
# Allowlist + alias — appelé via sudo -n depuis vzone-api uniquement.
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

if [[ ! "$UNIT" =~ ^[a-zA-Z0-9@._+-]+\.service$ ]] && [[ ! "$UNIT" =~ ^[a-zA-Z0-9@._+-]+$ ]]; then
  echo "unité invalide: ${UNIT}" >&2
  exit 2
fi

normalize="${UNIT%.service}"

# Alias UI / anciens noms → unités systemd réelles
case "$normalize" in
  vzone-celery|celery) normalize="vzone-worker" ;;
  vzone-celerybeat|celerybeat) normalize="vzone-beat" ;;
  pureftpd) normalize="pure-ftpd" ;;
  redis-server) normalize="redis" ;;
  ssh) normalize="sshd" ;;
  bind9) normalize="named" ;;
  mysql|mysqld) normalize="mysql" ;;
esac

ALLOWED=(
  nginx
  postgresql
  pgsql
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
  pureftpd
  vsftpd
  proftpd
  vzone-api
  vzone-celery
  vzone-celerybeat
  vzone-beat
  vzone-worker
)

ok=0
for a in "${ALLOWED[@]}"; do
  if [[ "$normalize" == "$a" || "${UNIT%.service}" == "$a" ]]; then
    ok=1
    break
  fi
done
# Aussi accepter le nom d'origine avant alias
orig="${UNIT%.service}"
for a in "${ALLOWED[@]}"; do
  if [[ "$orig" == "$a" ]]; then
    ok=1
    break
  fi
done
if [[ "$ok" -ne 1 ]]; then
  echo "unité non autorisée: ${UNIT}" >&2
  exit 3
fi

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

unit_load_state() {
  local u="$1"
  "$SYSTEMCTL" show -p LoadState --value "$u" 2>/dev/null || echo "not-found"
}

# Candidats à essayer (ordre) pour les services ambigus
candidates=("${normalize}.service")
case "$normalize" in
  mariadb|mysql|mysqld)
    candidates=("mariadb.service" "mysql.service" "mysqld.service")
    ;;
  redis)
    candidates=("redis-server.service" "redis.service")
    ;;
  sshd)
    candidates=("ssh.service" "sshd.service")
    ;;
  named)
    candidates=("named.service" "bind9.service")
    ;;
  pure-ftpd)
    candidates=("pure-ftpd.service" "pureftpd.service" "pure-ftpd.socket")
    ;;
  fail2ban)
    candidates=("fail2ban.service")
    ;;
  vzone-worker)
    candidates=("vzone-worker.service" "vzone-celery.service")
    ;;
  vzone-beat)
    candidates=("vzone-beat.service" "vzone-celerybeat.service")
    ;;
  postgresql)
    candidates=("postgresql.service")
    ;;
esac

TARGET=""
for c in "${candidates[@]}"; do
  st="$(unit_load_state "$c")"
  if [[ "$st" != "not-found" && -n "$st" ]]; then
    TARGET="$c"
    break
  fi
done

# Dernier recours : le nom demandé même si « not-found » (unit file peut apparaître au start)
if [[ -z "$TARGET" ]]; then
  TARGET="${normalize}.service"
  st="$(unit_load_state "$TARGET")"
  if [[ "$st" == "not-found" ]]; then
    # Essayer chaque candidat au start quand même (certains alias)
    for c in "${candidates[@]}"; do
      if "$SYSTEMCTL" cat "$c" >/dev/null 2>&1; then
        TARGET="$c"
        break
      fi
    done
  fi
fi

if [[ "$(unit_load_state "$TARGET")" == "not-found" ]] && ! "$SYSTEMCTL" cat "$TARGET" >/dev/null 2>&1; then
  echo "unité introuvable: ${TARGET} (candidats: ${candidates[*]})" >&2
  exit 5
fi

case "$ACTION" in
  status)
    "$SYSTEMCTL" is-active "$TARGET" 2>/dev/null || true
    "$SYSTEMCTL" show "$TARGET" -p LoadState -p ActiveState -p SubState -p UnitFileState --no-pager || true
    ;;
  *)
    # Ne pas faire échouer le script si is-active post-action renvoie non-zéro
    set +e
    "$SYSTEMCTL" "$ACTION" "$TARGET"
    rc=$?
    out_active="$("$SYSTEMCTL" is-active "$TARGET" 2>/dev/null)"
    set -e
    if [[ $rc -ne 0 ]]; then
      echo "échec ${ACTION} ${TARGET} (code ${rc})" >&2
      "$SYSTEMCTL" status "$TARGET" --no-pager -l 2>&1 | head -n 25 >&2 || true
      exit "$rc"
    fi
    echo "ok ${ACTION} ${TARGET} active=${out_active:-unknown}"
    ;;
esac
