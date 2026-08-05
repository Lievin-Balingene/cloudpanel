#!/usr/bin/env bash
# Répare les 403 Forbidden nginx sur les domaines clients.
#
# Causes fréquentes :
# 1) /home/<user> en 700/750 → www-data ne traverse pas jusqu'à public_html
# 2) ACL trop restrictives (other::---) après setfacl / restauration cPanel
# 3) docroot inexistant ou index manquant → « directory index forbidden »
# 4) vhost pointant vers une ancienne racine
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
DOMAINS_DIR="${VZONE_NGINX_DOMAINS_DIR:-/var/lib/vzone/nginx/domains}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1091
  set -a; source "$ENV_FILE"; set +a
  HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
  DOMAINS_DIR="${VZONE_NGINX_DOMAINS_DIR:-/var/lib/vzone/nginx/domains}"
fi

echo "=== V-zone repair-domains-403 ==="
echo "HOME_ROOT=${HOME_ROOT}"
echo "DOMAINS_DIR=${DOMAINS_DIR}"

fix_path_perms() {
  local path="$1"
  [[ -e "$path" ]] || return 0
  # Mode classique
  if [[ -d "$path" ]]; then
    chmod 755 "$path" 2>/dev/null || true
  else
    chmod 644 "$path" 2>/dev/null || true
  fi
  # ACL : garantir other::r-x / r-- pour nginx (www-data)
  if command -v setfacl >/dev/null 2>&1; then
    if [[ -d "$path" ]]; then
      setfacl -m o::rx "$path" 2>/dev/null || true
      setfacl -d -m o::rx "$path" 2>/dev/null || true
    else
      setfacl -m o::r "$path" 2>/dev/null || true
    fi
  fi
}

echo
echo "[1] Permissions /home + public_html"
chmod 755 "${HOME_ROOT}" 2>/dev/null || true
fix_path_perms "${HOME_ROOT}"

fixed=0
for home in "${HOME_ROOT}"/*; do
  [[ -d "$home" ]] || continue
  base="$(basename "$home")"
  case "$base" in
    lost+found|ubuntu|ec2-user) continue ;;
  esac

  fix_path_perms "$home"
  if [[ -d "$home/public_html" ]]; then
    fix_path_perms "$home/public_html"
    find "$home/public_html" -type d -exec chmod u=rwx,go=rx {} \; 2>/dev/null || true
    find "$home/public_html" -type f -exec chmod u=rw,go=r {} \; 2>/dev/null || true
    if command -v setfacl >/dev/null 2>&1; then
      # Appliquer other::rx récursivement sur le docroot (sans toucher aux ACL u:vzone)
      setfacl -R -m o::rx "$home/public_html" 2>/dev/null || true
      find "$home/public_html" -type f -exec setfacl -m o::r {} \; 2>/dev/null || true
    fi
  else
    mkdir -p "$home/public_html"
    fix_path_perms "$home/public_html"
  fi

  # Index minimal si aucun index (évite 403 directory index)
  if [[ ! -f "$home/public_html/index.html" && ! -f "$home/public_html/index.php" && ! -f "$home/public_html/index.htm" ]]; then
    cat > "$home/public_html/index.html" <<'HTML'
<!DOCTYPE html><html><head><meta charset="utf-8"><title>Site ready</title></head>
<body style="font-family:system-ui;padding:2rem"><h1>Site ready</h1>
<p>Document root is reachable. Upload your site files to public_html.</p></body></html>
HTML
    chmod 644 "$home/public_html/index.html" 2>/dev/null || true
    echo "  + index.html créé dans $home/public_html"
  fi

  # Propriétaire panel (sans refermer other)
  if id vzone >/dev/null 2>&1; then
    chown -R vzone:vzone "$home" 2>/dev/null || true
    chmod 755 "$home" 2>/dev/null || true
    [[ -d "$home/public_html" ]] && chmod 755 "$home/public_html" 2>/dev/null || true
  fi

  fixed=$((fixed + 1))
  mode="$(stat -c '%a' "$home" 2>/dev/null || echo '?')"
  www_ok="KO"
  if sudo -u www-data test -x "$home" && sudo -u www-data test -r "$home/public_html"; then
    www_ok="OK"
  fi
  echo "  $home mode=${mode} www-data=${www_ok}"
  if [[ "$www_ok" != "OK" ]]; then
    namei -l "$home/public_html" 2>/dev/null || true
    getfacl -p "$home" 2>/dev/null | head -n 20 || true
  fi
done
echo "[1] ${fixed} home(s) traités"

echo
echo "[2] Resync vhosts Django → ${DOMAINS_DIR}"
PY="${VZONE_ROOT}/backend/.venv/bin/python"
if [[ -x "$PY" ]]; then
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  "$PY" - <<'PY' || true
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vzone.settings.production")
import django
django.setup()
from apps.domains.vhosts import sync_all_domain_vhosts
from apps.files.services import ensure_cpanel_tree, personal_home
from apps.accounts.models import User
n = 0
for u in User.objects.exclude(role="administrator"):
    try:
        ensure_cpanel_tree(personal_home(u))
        n += 1
    except Exception as exc:
        print(f"  warn home {u.username}: {exc}")
print(f"  ensure_cpanel_tree: {n} comptes")
count = sync_all_domain_vhosts()
print(f"  sync_all_domain_vhosts: {count}")
PY
else
  echo "  (python venv absent — skip sync Django)"
fi

echo
echo "[3] Vérification des roots nginx"
ok_count=0
fail_count=0
if [[ -d "$DOMAINS_DIR" ]]; then
  for conf in "${DOMAINS_DIR}"/*.conf; do
    [[ -f "$conf" ]] || continue
    [[ "$(basename "$conf")" == ".keep.conf" ]] && continue
    DN="$(awk '/server_name/{print $2; exit}' "$conf" | tr -d ';')"
    ROOT="$(awk '/^\s*root /{print $2; exit}' "$conf" | tr -d ';')"
    [[ -z "$DN" || "$DN" == "_" ]] && continue
    if [[ -z "$ROOT" ]]; then
      echo "  $DN — PAS DE root dans le conf"
      fail_count=$((fail_count + 1))
      continue
    fi
    if [[ ! -d "$ROOT" ]]; then
      echo "  $DN — root MANQUANT: $ROOT"
      mkdir -p "$ROOT" 2>/dev/null || true
      fix_path_perms "$ROOT"
      echo "<h1>Site ready</h1>" > "${ROOT}/index.html" 2>/dev/null || true
      fail_count=$((fail_count + 1))
      continue
    fi
    CODE="$(curl -sk -o /dev/null -w '%{http_code}' -H "Host: ${DN}" "http://127.0.0.1/" 2>/dev/null || echo 000)"
    if [[ "$CODE" == "403" ]]; then
      echo "  $DN → HTTP 403 (root=$ROOT)"
      tail -n 5 "/var/log/nginx/${DN//./_}.error.log" 2>/dev/null || true
      tail -n 5 "/var/log/nginx/$(echo "$DN" | tr '.' '_').error.log" 2>/dev/null || true
      # Dernière chance perms
      fix_path_perms "$(dirname "$ROOT")"
      fix_path_perms "$ROOT"
      find "$ROOT" -maxdepth 1 -type f -exec chmod 644 {} \; 2>/dev/null || true
      fail_count=$((fail_count + 1))
    else
      echo "  $DN → HTTP ${CODE} (root=$ROOT)"
      ok_count=$((ok_count + 1))
    fi
  done
else
  echo "  Dossier vhosts absent: $DOMAINS_DIR"
fi

echo
echo "[4] nginx -t + reload"
if nginx -t 2>&1; then
  systemctl reload nginx 2>/dev/null || service nginx reload 2>/dev/null || true
fi

echo
echo "[5] Re-test après reload"
if [[ -d "$DOMAINS_DIR" ]]; then
  for conf in "${DOMAINS_DIR}"/*.conf; do
    [[ -f "$conf" ]] || continue
    [[ "$(basename "$conf")" == ".keep.conf" ]] && continue
    DN="$(awk '/server_name/{print $2; exit}' "$conf" | tr -d ';')"
    [[ -z "$DN" || "$DN" == "_" ]] && continue
    CODE="$(curl -sk -o /dev/null -w '%{http_code}' -H "Host: ${DN}" "http://127.0.0.1/" 2>/dev/null || echo 000)"
    echo "  $DN → HTTP ${CODE}"
  done
fi

echo
echo "=== Fin ==="
echo "Si 403 persiste, coller la sortie de :"
echo "  sudo tail -n 40 /var/log/nginx/*.error.log | grep -i 'permission\\|directory index\\|forbidden'"
echo "  sudo -u www-data namei -l /home/USER/public_html"
echo "  grep -E 'root |server_name' /var/lib/vzone/nginx/domains/DOMAINE.conf"
