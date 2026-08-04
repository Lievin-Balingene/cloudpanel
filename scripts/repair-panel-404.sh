#!/usr/bin/env bash
# Répare le 404 global : souvent k3s/Traefik qui a volé les ports 80/443 à nginx.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
REPO_DIR="${REPO_DIR:-/opt/vzone-src}"
[[ -d "$REPO_DIR" ]] || REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== repair-panel-404 ==="

echo "[0] Qui écoute 80/443 ?"
ss -tlnp 2>/dev/null | grep -E ':80\s|:443\s' || netstat -tlnp 2>/dev/null | grep -E ':80 |:443 ' || true

PORT80_PROC="$(ss -tlnp 2>/dev/null | grep -E ':80\s' | head -n1 || true)"
if echo "$PORT80_PROC" | grep -qiE 'k3s|traefik|svclb|docker|containerd'; then
  echo "[!] CONFLIT: le port 80 n'est PAS nginx — c'est probablement k3s/Traefik."
  echo "    Réponse typique: '404 page not found' (Go/Traefik)."
  echo "[0b] Désactivation Traefik + ServiceLB k3s (le panel garde 80/443)…"

  mkdir -p /etc/rancher/k3s
  CONFIG=/etc/rancher/k3s/config.yaml
  if [[ ! -f "$CONFIG" ]]; then
    cat > "$CONFIG" <<'EOF'
# V-zone : nginx panel conserve 80/443
disable:
  - traefik
  - servicelb
EOF
  else
    # Assurer disable traefik/servicelb sans casser le reste
    if ! grep -q 'traefik' "$CONFIG" 2>/dev/null; then
      if grep -q '^disable:' "$CONFIG"; then
        grep -q 'traefik' "$CONFIG" || sed -i '/^disable:/a\  - traefik' "$CONFIG"
        grep -q 'servicelb' "$CONFIG" || sed -i '/^disable:/a\  - servicelb' "$CONFIG"
      else
        cat >> "$CONFIG" <<'EOF'

disable:
  - traefik
  - servicelb
EOF
      fi
    fi
  fi

  # Stopper les pods/services qui tiennent 80/443 immédiatement
  if command -v kubectl >/dev/null 2>&1; then
    export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
    kubectl -n kube-system delete helmchart traefik --ignore-not-found 2>/dev/null || true
    kubectl -n kube-system delete deploy,svc,ds -l app.kubernetes.io/name=traefik --ignore-not-found 2>/dev/null || true
    kubectl -n kube-system delete svc traefik --ignore-not-found 2>/dev/null || true
    # svclb DaemonSets (klipper) sur 80/443
    kubectl -n kube-system delete ds -l svccontroller.k3s.cattle.io/svcname --ignore-not-found 2>/dev/null || true
    kubectl -n kube-system get ds 2>/dev/null | awk '/svclb/ {print $1}' | while read -r ds; do
      kubectl -n kube-system delete ds "$ds" --ignore-not-found 2>/dev/null || true
    done
  fi

  systemctl restart k3s 2>/dev/null || systemctl restart k3s-agent 2>/dev/null || true
  sleep 3

  # Libérer de force si un processus k3s tient encore 80
  for pid in $(ss -tlnp 2>/dev/null | grep -E ':80\s' | grep -oP 'pid=\K[0-9]+' | sort -u); do
    proc="$(ps -p "$pid" -o comm= 2>/dev/null || true)"
    if echo "$proc" | grep -qiE 'k3s|traefik|svclb|lb-'; then
      echo "  arrêt pid $pid ($proc) qui bloque :80"
      kill "$pid" 2>/dev/null || true
    fi
  done
  sleep 1
fi

# Docker qui publie 80
if command -v docker >/dev/null 2>&1; then
  mapfile -t DOCKER80 < <(docker ps --format '{{.ID}} {{.Names}} {{.Ports}}' 2>/dev/null | grep -E '0\.0\.0\.0:80->|:80->' || true)
  if ((${#DOCKER80[@]})); then
    echo "[!] Conteneurs Docker sur le port 80 :"
    printf '  %s\n' "${DOCKER80[@]}"
    echo "  Arrêtez-les ou changez le mapping de port (le panel nginx doit garder 80/443)."
  fi
fi

echo "[1] Frontend dist"
if [[ ! -f "${VZONE_ROOT}/frontend/dist/index.html" ]]; then
  bash "${REPO_DIR}/scripts/repair-frontend.sh"
fi
ls -la "${VZONE_ROOT}/frontend/dist/index.html"
chmod a+x /opt /opt/vzone /opt/vzone/frontend "${VZONE_ROOT}/frontend/dist" 2>/dev/null || true
chmod -R a+rX "${VZONE_ROOT}/frontend/dist" || true

echo "[2] Purge conf panel conflictuelles + vhosts panel"
rm -fv /etc/nginx/sites-enabled/vzone \
       /etc/nginx/sites-available/vzone \
       /etc/nginx/conf.d/vzone.conf 2>/dev/null || true
for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
  [[ -e "$f" ]] || continue
  base="$(basename "$f")"
  [[ "$base" == "zz-vzone-panel.conf" ]] && continue
  [[ "$base" == "vzone-domains-include.conf" || "$base" == "vzone-map-upgrade.conf" ]] && continue
  if grep -q "default_server" "$f" 2>/dev/null; then
    echo "  disable $f"
    mv -f "$f" "${f}.disabled-by-vzone" 2>/dev/null || rm -fv "$f"
  fi
done
# Retirer tout vhost domaine qui mentionne le hostname panel
DOMAINS_DIR="${VZONE_NGINX_DOMAINS_DIR:-/var/lib/vzone/nginx/domains}"
PANEL_HOSTS="${VZONE_PANEL_HOSTNAMES:-vpanel.vzonecloud.co.uk}"
if [[ -f /etc/vzone/vzone.env ]]; then
  set -a; # shellcheck disable=SC1091
  source /etc/vzone/vzone.env; set +a
  PANEL_HOSTS="${VZONE_PANEL_HOSTNAMES:-$PANEL_HOSTS}"
fi
for h in ${PANEL_HOSTS//,/ }; do
  [[ -n "$h" ]] || continue
  safe="$(echo "$h" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]/_/g')"
  rm -fv "${DOMAINS_DIR}/${safe}.conf" 2>/dev/null || true
done

echo "[3] Réinstalle nginx panel + redémarrage"
bash "${REPO_DIR}/scripts/ensure-nginx.sh" "${VZONE_ROOT}/deploy/nginx/vzone.conf"
systemctl enable --now nginx
systemctl restart nginx

sleep 2
echo "[4] Ports après réparation"
ss -tlnp 2>/dev/null | grep -E ':80\s|:443\s' || true

echo "[5] Test /login"
code="$(curl -sk -o /tmp/vzone-login.body -w "%{http_code}" -H "Host: vpanel.vzonecloud.co.uk" "http://127.0.0.1/login" || true)"
echo "  HTTP $code"
head -c 160 /tmp/vzone-login.body; echo
if [[ "$code" == "200" ]] && grep -qiE 'DOCTYPE|id="root"|vite|V-zone' /tmp/vzone-login.body; then
  echo "[OK] Panel SPA servie par nginx"
else
  echo "[ÉCHEC] Toujours pas OK."
  echo "  ss -tlnp | grep -E ':80|:443'"
  ss -tlnp 2>/dev/null | grep -E ':80\s|:443\s' || true
  echo "  Si k3s/Traefik revient : sudo k3s server --disable traefik  (ou config.yaml) + redémarrer k3s"
  exit 1
fi

echo "=== Terminé — Ctrl+F5 sur https://vpanel.vzonecloud.co.uk/login ==="
