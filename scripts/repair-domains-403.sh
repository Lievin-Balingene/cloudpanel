#!/usr/bin/env bash
# Répare les 403 Forbidden nginx sur les domaines clients.
# Cause fréquente : /home/<user> en 700/750 → www-data ne peut pas traverser jusqu'à public_html.
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
if [[ -f /etc/vzone/vzone.env ]]; then
  # shellcheck disable=SC1091
  set -a; source /etc/vzone/vzone.env; set +a
  HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
fi

echo "[vzone] Réparation 403 domaines — homes sous ${HOME_ROOT}"

fixed=0
for home in "${HOME_ROOT}"/*; do
  [[ -d "$home" ]] || continue
  base="$(basename "$home")"
  # Ne pas toucher aux dossiers système éventuels
  case "$base" in
    lost+found|ubuntu|ec2-user) continue ;;
  esac

  chmod 755 "$home" 2>/dev/null || true
  if [[ -d "$home/public_html" ]]; then
    chmod 755 "$home/public_html" 2>/dev/null || true
    # Fichiers lisibles, dossiers traversables (sans tout ouvrir en 777)
    find "$home/public_html" -type d -exec chmod u=rwx,go=rx {} \; 2>/dev/null || true
    find "$home/public_html" -type f -exec chmod u=rw,go=r {} \; 2>/dev/null || true
  fi
  fixed=$((fixed + 1))
  echo "  OK $home ($(stat -c '%a' "$home" 2>/dev/null || echo '?'))"
done

# /home lui-même doit être traversable
chmod 755 "${HOME_ROOT}" 2>/dev/null || true

echo "[vzone] ${fixed} home(s) corrigé(s)"

# Test rapide : www-data peut-il lister un public_html ?
sample=""
for home in "${HOME_ROOT}"/*/public_html; do
  [[ -d "$home" ]] || continue
  sample="$home"
  break
done
if [[ -n "$sample" ]]; then
  if sudo -u www-data test -x "$(dirname "$sample")" && sudo -u www-data test -r "$sample"; then
    echo "[vzone] www-data OK sur $sample"
  else
    echo "[vzone] ALERTE: www-data ne peut toujours pas lire $sample"
    namei -l "$sample" || true
  fi
fi

if [[ -x /opt/vzone-src/scripts/ensure-nginx.sh ]]; then
  bash /opt/vzone-src/scripts/ensure-nginx.sh || true
elif [[ -x /opt/vzone/scripts/ensure-nginx.sh ]]; then
  bash /opt/vzone/scripts/ensure-nginx.sh || true
fi

echo "[vzone] Terminé. Vérifiez : curl -sI -H 'Host: votredomaine' http://127.0.0.1/"
