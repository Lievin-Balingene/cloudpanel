#!/usr/bin/env bash
# Garde SMTP: si milter OpenDKIM provoque 451 / unavailable → coupe les milters.
# Installé par repair-smtp / install-mail / update. Tourne via systemd timer.
set -uo pipefail
[[ ${EUID:-0} -eq 0 ]] || exit 0

FLAG="/var/lib/vzone/smtp-guard.last-strip"
LOG="${MAIL_LOG:-/var/log/mail.log}"
[[ -f "$LOG" ]] || LOG="/var/log/maillog"
[[ -f "$LOG" ]] || exit 0

# Déjà milters vides partout ?
if ! grep -qE 'smtpd_milters=.+' /etc/postfix/master.cf 2>/dev/null \
  && [[ -z "$(postconf -h smtpd_milters 2>/dev/null)" ]] \
  && [[ -z "$(postconf -h non_smtpd_milters 2>/dev/null)" ]]; then
  exit 0
fi

# Signatures d'échec milter / OpenDKIM dans les 3 dernières minutes
WINDOW_SEC=180
NOW=$(date +%s)
hit=0
if command -v journalctl >/dev/null 2>&1; then
  if journalctl -u postfix -u opendkim --since "3 min ago" --no-pager 2>/dev/null \
    | grep -qiE 'milter|opendkim.*(fail|error|tempfail)|4\.7\.1|Service unavailable|DKIM.*fail'; then
    hit=1
  fi
fi
if [[ "$hit" -eq 0 && -f "$LOG" ]]; then
  # tail récent
  if tail -n 200 "$LOG" 2>/dev/null | grep -qiE 'milter.*(reject|tempfail|timeout)|opendkim.*(fail|error)|451 4\.7\.1|Service unavailable'; then
    hit=1
  fi
fi

# Aussi: socket/inet milter down alors que master.cf pointe encore dessus
if grep -qE 'smtpd_milters=.*(opendkim|8891)' /etc/postfix/master.cf 2>/dev/null; then
  if ! ss -ltn 2>/dev/null | grep -q ':8891 ' && ! [[ -S /var/spool/postfix/opendkim/opendkim.sock ]]; then
    hit=1
  fi
fi

[[ "$hit" -eq 1 ]] || exit 0

# Anti-boucle: max 1 strip / 60s
if [[ -f "$FLAG" ]]; then
  last=$(cat "$FLAG" 2>/dev/null || echo 0)
  (( NOW - last < 60 )) && exit 0
fi

REPO_DIR="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
if [[ -x "${REPO_DIR}/scripts/repair-smtp.sh" ]]; then
  logger -t vzone-smtp-guard "Milter/SMTP fail détecté — repair-smtp automatique"
  bash "${REPO_DIR}/scripts/repair-smtp.sh" >/tmp/vzone-smtp-guard.log 2>&1 || true
else
  postconf -e "smtpd_milters=" "non_smtpd_milters=" "milter_default_action=accept"
  sed -i -E 's/^([ \t]*-o[ \t]+smtpd_milters=).*/\1/' /etc/postfix/master.cf 2>/dev/null || true
  sed -i '/milter_macro_daemon_name=ORIGINATING/d' /etc/postfix/master.cf 2>/dev/null || true
  systemctl reload postfix 2>/dev/null || systemctl restart postfix 2>/dev/null || true
  logger -t vzone-smtp-guard "Milters coupés (fallback)"
fi
mkdir -p "$(dirname "$FLAG")"
echo "$NOW" > "$FLAG"
