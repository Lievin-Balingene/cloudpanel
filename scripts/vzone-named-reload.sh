#!/usr/bin/env bash
# Recharge BIND après export des zones V-zone.
set -euo pipefail

FLAG="${VZONE_DNS_RELOAD_FLAG:-/var/lib/vzone/named/reload.requested}"
NAMED_DIR="${VZONE_DNS_DIR:-/var/lib/vzone/named}"

rm -f "${FLAG}" 2>/dev/null || true

# Droits : named doit lire, vzone doit écrire
chgrp -R bind "${NAMED_DIR}" 2>/dev/null || chgrp -R named "${NAMED_DIR}" 2>/dev/null || true
chmod -R g+rwX "${NAMED_DIR}" 2>/dev/null || true

if command -v named-checkconf >/dev/null 2>&1; then
  named-checkconf || {
    echo "[vzone-named-reload] named-checkconf a échoué" >&2
    exit 1
  }
fi

# Ne jamais recharger des zones TXT/SOA invalides (cause historique de SERVFAIL public)
ZONES_DIR="${NAMED_DIR}/zones"
if [[ -d "${ZONES_DIR}" ]] && command -v named-checkzone >/dev/null 2>&1; then
  shopt -s nullglob
  for zf in "${ZONES_DIR}"/*.zone; do
    zname="$(basename "${zf}" .zone)"
    if ! named-checkzone "${zname}" "${zf}" >/dev/null 2>&1; then
      echo "[vzone-named-reload] zone invalide retirée: ${zname}" >&2
      rm -f "${zf}"
      # Retirer du zones.conf si présent
      if [[ -f "${NAMED_DIR}/zones.conf" ]]; then
        # Régénération minimale : commenter le bloc zone (sync suivant réparera)
        python3 - "${NAMED_DIR}/zones.conf" "${zname}" <<'PY' || true
import pathlib, sys
conf, name = pathlib.Path(sys.argv[1]), sys.argv[2]
text = conf.read_text(encoding="utf-8")
out, skip, depth = [], False, 0
for line in text.splitlines(True):
    if (not skip) and f'zone "{name}"' in line:
        skip, depth = True, line.count("{") - line.count("}")
        continue
    if skip:
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            skip = False
        continue
    out.append(line)
conf.write_text("".join(out), encoding="utf-8")
PY
      fi
    fi
  done
  shopt -u nullglob
fi

if command -v rndc >/dev/null 2>&1; then
  rndc reconfig 2>/dev/null || true
  rndc reload 2>/dev/null || true
fi

systemctl reload named 2>/dev/null || systemctl reload bind9 2>/dev/null || \
  systemctl restart named 2>/dev/null || systemctl restart bind9 2>/dev/null || true

echo "[vzone-named-reload] OK"
