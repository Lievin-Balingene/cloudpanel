#!/usr/bin/env bash
# Wrapper sendmail pour PHP mail() — rate-limit + journalisation.
# Empêche les sites compromis (WordPress, etc.) de spammer via mail()
# et de faire lister l'IP en Spamhaus CSS.
#
# Installé comme /usr/local/sbin/vzone-php-sendmail
set -euo pipefail

REAL_SENDMAIL="${VZONE_REAL_SENDMAIL:-/usr/sbin/sendmail}"
[[ -x "$REAL_SENDMAIL" ]] || REAL_SENDMAIL="$(command -v sendmail || true)"
[[ -n "${REAL_SENDMAIL}" && -x "${REAL_SENDMAIL}" ]] || {
  echo "vzone-php-sendmail: sendmail introuvable" >&2
  exit 75
}

STATE_DIR="${VZONE_PHP_MAIL_STATE:-/var/lib/vzone/php-mail}"
LOG_DIR="${VZONE_LOG:-/var/log/vzone}"
LIMIT_PER_HOUR="${VZONE_PHP_MAIL_LIMIT:-40}"
UID_NUM="$(id -u)"
HOUR_KEY="$(date -u +%Y%m%d%H)"
COUNTER_FILE="${STATE_DIR}/uid-${UID_NUM}.${HOUR_KEY}"

mkdir -p "$STATE_DIR" "$LOG_DIR" 2>/dev/null || true
chmod 1777 "$STATE_DIR" 2>/dev/null || true

count=0
if [[ -f "$COUNTER_FILE" ]]; then
  count="$(tr -cd '0-9' < "$COUNTER_FILE" 2>/dev/null || echo 0)"
  [[ -n "$count" ]] || count=0
fi

if (( count >= LIMIT_PER_HOUR )); then
  echo "$(date -Is) uid=${UID_NUM} user=$(id -un 2>/dev/null || echo ?) DENY limit=${LIMIT_PER_HOUR}/h" \
    >> "${LOG_DIR}/php-mail.log" 2>/dev/null || true
  echo "vzone-php-sendmail: rate limit exceeded (${LIMIT_PER_HOUR}/hour)" >&2
  exit 75
fi

echo $((count + 1)) > "$COUNTER_FILE" 2>/dev/null || true
echo "$(date -Is) uid=${UID_NUM} user=$(id -un 2>/dev/null || echo ?) OK count=$((count + 1))" \
  >> "${LOG_DIR}/php-mail.log" 2>/dev/null || true

# Nettoyage compteurs > 3 h
find "$STATE_DIR" -type f -name 'uid-*' -mmin +180 -delete 2>/dev/null || true

exec "$REAL_SENDMAIL" "$@"
