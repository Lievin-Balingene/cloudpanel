#!/usr/bin/env bash
# Audit réputation : PTR, Spamhaus ZEN/CSS, DBL domaines mail.
# Usage: sudo bash vzone-mail-reputation-check.sh [--json]
set -euo pipefail

JSON=0
[[ "${1:-}" == "--json" ]] && JSON=1

PUBLIC_IP=""
PUBLIC_IP="$(curl -4 -fsS --max-time 5 https://ifconfig.me 2>/dev/null || true)"
[[ -z "$PUBLIC_IP" ]] && PUBLIC_IP="$(curl -4 -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
[[ -z "$PUBLIC_IP" ]] && PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"

rev_ip() {
  local ip="$1"
  awk -F. '{print $4"."$3"."$2"."$1}' <<<"$ip"
}

listed_codes=""
zen_status="ok"
dbl_hits=()
ptr_host=""
ptr_ok=0
warnings=()

if [[ -n "$PUBLIC_IP" ]]; then
  ptr_host="$(dig +short -x "$PUBLIC_IP" 2>/dev/null | head -n1 | sed 's/\.$//')"
  if [[ -n "$ptr_host" ]]; then
    if [[ "$ptr_host" == "$HOSTNAME_FQDN" ]] || dig +short A "$ptr_host" 2>/dev/null | grep -qx "$PUBLIC_IP"; then
      ptr_ok=1
    else
      warnings+=("PTR ${ptr_host} ne matche pas le hostname ${HOSTNAME_FQDN}")
    fi
  else
    warnings+=("PTR / rDNS manquant pour ${PUBLIC_IP} — cause fréquente Spamhaus CSS")
  fi

  rev="$(rev_ip "$PUBLIC_IP")"
  listed_codes="$(dig +short "${rev}.zen.spamhaus.org" A 2>/dev/null | tr '\n' ' ' | xargs || true)"
  if [[ -n "$listed_codes" ]]; then
    zen_status="listed"
    if echo "$listed_codes" | grep -q '127.0.0.3'; then
      warnings+=("IP listée Spamhaus CSS (127.0.0.3) — https://check.spamhaus.org/")
    else
      warnings+=("IP listée Spamhaus ZEN: ${listed_codes} — https://check.spamhaus.org/")
    fi
  elif dig +short "${rev}.zen.spamhaus.org" A 2>/dev/null | grep -qi 'refused\|servfail'; then
    zen_status="query_blocked"
    warnings+=("Requête Spamhaus refusée (utilisez le résolveur système / compte Spamhaus DQS)")
  fi
fi

# DBL pour domaines mail actifs (best-effort)
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a; # shellcheck disable=SC1090
  source "$ENV_FILE"; set +a
fi
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" ]]; then
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-vzone.settings.production}"
  domains="$(
    "${VZONE_ROOT}/backend/.venv/bin/python" - <<'PY' 2>/dev/null || true
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vzone.settings.production")
django.setup()
from apps.email.models import MailDomain
print("\n".join(MailDomain.objects.filter(is_active=True).values_list("name", flat=True)[:50]))
PY
  )"
  while IFS= read -r d; do
    [[ -z "$d" ]] && continue
    hit="$(dig +short "${d}.dbl.spamhaus.org" A 2>/dev/null | tr '\n' ' ' | xargs || true)"
    if [[ -n "$hit" ]]; then
      dbl_hits+=("$d:$hit")
      warnings+=("Domaine ${d} listé Spamhaus DBL (${hit})")
    fi
  done <<<"$domains"
fi

smtp_restrict=0
if [[ -f /var/lib/vzone/smtp-restrictions/enabled ]]; then
  [[ "$(tr -d '[:space:]' </var/lib/vzone/smtp-restrictions/enabled)" == "1" ]] && smtp_restrict=1
fi
[[ "$smtp_restrict" -eq 0 ]] && warnings+=("SMTP Restrictions désactivées — activez-les (WHM → SMTP Restrictions)")

if [[ "$JSON" -eq 1 ]]; then
  printf '{'
  printf '"ip":"%s","hostname":"%s","ptr":"%s","ptr_ok":%s,' \
    "$PUBLIC_IP" "$HOSTNAME_FQDN" "$ptr_host" "$([[ $ptr_ok -eq 1 ]] && echo true || echo false)"
  printf '"spamhaus_zen":"%s","spamhaus_codes":"%s","smtp_restrictions":%s,' \
    "$zen_status" "$listed_codes" "$([[ $smtp_restrict -eq 1 ]] && echo true || echo false)"
  printf '"dbl":['
  first=1
  for h in "${dbl_hits[@]:-}"; do
    [[ -z "$h" ]] && continue
    [[ $first -eq 1 ]] || printf ','
    first=0
    printf '"%s"' "$h"
  done
  printf '],"warnings":['
  first=1
  for w in "${warnings[@]:-}"; do
    [[ -z "$w" ]] && continue
    [[ $first -eq 1 ]] || printf ','
    first=0
    printf '"%s"' "${w//\"/\\\"}"
  done
  printf ']}\n'
  exit 0
fi

echo "=== AngaPanel mail reputation check ==="
echo "IP:        ${PUBLIC_IP:-?}"
echo "Hostname:  ${HOSTNAME_FQDN}"
echo "PTR:       ${ptr_host:-ABSENT} $([[ $ptr_ok -eq 1 ]] && echo OK || echo WARN)"
echo "Spamhaus:  ${zen_status} ${listed_codes}"
echo "SMTP restr:$([[ $smtp_restrict -eq 1 ]] && echo ON || echo OFF)"
if ((${#dbl_hits[@]})); then
  echo "DBL hits:  ${dbl_hits[*]}"
fi
if ((${#warnings[@]})); then
  echo
  echo "Warnings:"
  for w in "${warnings[@]}"; do echo "  - $w"; done
else
  echo
  echo "Aucune alerte critique détectée."
fi
echo
echo "Actions: repair-mail-reputation.sh · PTR chez l'hébergeur · https://check.spamhaus.org/"
