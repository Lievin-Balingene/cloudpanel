#!/usr/bin/env bash
# Ouvre HTTP/HTTPS depuis l'extérieur (timeout navigateur / ERR_CONNECTION_TIMED_OUT).
# Causes fréquentes : UFW, firewalld, iptables k3s après install Kubernetes.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

echo "=== repair-external-access (ports 80/443) ==="

echo "[1] Écoute locale"
ss -tlnp | grep -E ':80\s|:443\s' || true

echo "[2] UFW"
if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH || ufw allow 22/tcp || true
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
  # S'assurer que le firewall n'est pas "deny incoming" sans règles http
  ufw status verbose || true
  ufw --force enable || true
  ufw reload || true
  echo "  UFW: 80/443 autorisés"
else
  echo "  UFW absent"
fi

echo "[3] firewalld"
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
  firewall-cmd --permanent --add-service=http || true
  firewall-cmd --permanent --add-service=https || true
  firewall-cmd --permanent --add-service=ssh || true
  firewall-cmd --reload || true
  echo "  firewalld: http/https OK"
fi

echo "[4] iptables INPUT (accepter 80/443 explicitement)"
# k3s injecte souvent des chaînes qui droppent le trafic externe vers nginx
for proto in iptables ip6tables; do
  command -v "$proto" >/dev/null 2>&1 || continue
  # Éviter les doublons : supprimer puis réinsérer en tête
  while $proto -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; do
    $proto -D INPUT -p tcp --dport 80 -j ACCEPT || break
  done
  while $proto -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null; do
    $proto -D INPUT -p tcp --dport 443 -j ACCEPT || break
  done
  $proto -I INPUT 1 -p tcp --dport 80 -j ACCEPT
  $proto -I INPUT 1 -p tcp --dport 443 -j ACCEPT
  # RELATED/ESTABLISHED en tête si absent
  if ! $proto -C INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null \
     && ! $proto -C INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; then
    $proto -I INPUT 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null \
      || $proto -I INPUT 1 -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null \
      || true
  fi
  echo "  $proto: ACCEPT tcp/80 et tcp/443 en tête de INPUT"
done

echo "[5] nftables (si utilisé)"
if command -v nft >/dev/null 2>&1; then
  # Best-effort : afficher les drops sur 80/443
  nft list ruleset 2>/dev/null | grep -E 'dport (80|443)|drop|reject' | head -n 40 || true
fi

echo "[6] k3s : s'assurer que Traefik/ServiceLB restent off"
if systemctl is-active --quiet k3s 2>/dev/null || [[ -d /etc/rancher/k3s ]]; then
  mkdir -p /etc/rancher/k3s
  if [[ ! -f /etc/rancher/k3s/config.yaml ]] || ! grep -q traefik /etc/rancher/k3s/config.yaml 2>/dev/null; then
    cat > /etc/rancher/k3s/config.yaml <<'EOF'
disable:
  - traefik
  - servicelb
EOF
  fi
fi

echo "[7] nginx up"
systemctl enable --now nginx 2>/dev/null || true
systemctl restart nginx 2>/dev/null || true

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "[8] Tests"
echo "  local : $(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1/login || echo fail)"
if [[ -n "$HOST_IP" ]]; then
  echo "  via IP locale ($HOST_IP) : $(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 --interface "$HOST_IP" "http://${HOST_IP}/login" 2>/dev/null || echo fail)"
fi

echo
echo "=== Suite ==="
echo "1) Testez depuis VOTRE PC (pas le serveur) :"
echo "   https://vpanel.vzonecloud.co.uk/login"
echo "   https://${HOST_IP}/login"
echo "2) Si timeout persiste : ouvrez 80 et 443 dans le pare-feu Contabo"
echo "   (Customer Control Panel → VPS → Network / Firewall)."
echo "3) Diagnostic serveur :"
echo "   iptables -L INPUT -n -v | head -40"
echo "   ufw status verbose"
