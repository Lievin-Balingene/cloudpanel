#!/usr/bin/env bash
# Ouvre HTTP/HTTPS/DNS depuis l'extérieur (timeout navigateur / LE DNS timeout).
# Causes fréquentes : UFW, firewalld, règles REJECT kube-proxy (LoadBalancer k3s), Contabo.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo "=== repair-external-access (ports 80/443/53) ==="

echo "[1] Écoute locale"
ss -tlnp | grep -E ':80\s|:443\s|:53\s' || true
ss -ulnp | grep -E ':53\s' || true

echo "[2] UFW"
if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH || ufw allow 22/tcp || true
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
  ufw allow 53/tcp || true
  ufw allow 53/udp || true
  ufw status verbose || true
  ufw --force enable || true
  ufw reload || true
  echo "  UFW: 80/443/53 autorisés"
else
  echo "  UFW absent"
fi

echo "[3] firewalld"
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
  firewall-cmd --permanent --add-service=http || true
  firewall-cmd --permanent --add-service=https || true
  firewall-cmd --permanent --add-service=ssh || true
  firewall-cmd --permanent --add-service=dns || true
  firewall-cmd --reload || true
  echo "  firewalld: http/https/dns OK"
fi

echo "[4] k3s : désactiver Traefik/ServiceLB + supprimer services LB sur 80/443"
if systemctl is-active --quiet k3s 2>/dev/null || [[ -d /etc/rancher/k3s ]]; then
  mkdir -p /etc/rancher/k3s
  cat > /etc/rancher/k3s/config.yaml <<'EOF'
# V-zone : nginx panel conserve 80/443 — pas de Traefik/ServiceLB
disable:
  - traefik
  - servicelb
EOF

  if command -v kubectl >/dev/null 2>&1 && [[ -f "$KUBECONFIG" ]]; then
    while read -r ns name; do
      [[ -z "${ns:-}" || -z "${name:-}" ]] && continue
      echo "  delete LoadBalancer $ns/$name"
      kubectl -n "$ns" delete svc "$name" --ignore-not-found 2>/dev/null || true
    done < <(kubectl get svc -A -o jsonpath='{range .items[?(@.spec.type=="LoadBalancer")]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' 2>/dev/null || true)

    kubectl -n kube-system delete helmchart traefik --ignore-not-found 2>/dev/null || true
    kubectl -n kube-system delete deploy,svc,ds -l app.kubernetes.io/name=traefik --ignore-not-found 2>/dev/null || true
    kubectl -n kube-system delete svc traefik --ignore-not-found 2>/dev/null || true
    kubectl -n kube-system get ds -o name 2>/dev/null | grep -i svclb | while read -r ds; do
      echo "  delete $ds"
      kubectl -n kube-system delete "$ds" --ignore-not-found 2>/dev/null || true
    done
  fi
fi

echo "[5] Supprimer les REJECT kube-proxy sur ${HOST_IP:-host}:80/443/53"
remove_kube_rejects() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || return 0
  if $cmd -L KUBE-EXTERNAL-SERVICES -n >/dev/null 2>&1; then
    local line
    while read -r line; do
      [[ -z "$line" ]] && continue
      local num="${line%% *}"
      if echo "$line" | grep -qE "dpt:(80|443|53).*reject|reject.*dpt:(80|443|53)"; then
        echo "  $cmd -D KUBE-EXTERNAL-SERVICES $num ($line)"
        $cmd -D KUBE-EXTERNAL-SERVICES "$num" 2>/dev/null || true
      elif [[ -n "${HOST_IP:-}" ]] && echo "$line" | grep -q "$HOST_IP" && echo "$line" | grep -qE 'dpt:(80|443|53)'; then
        echo "  $cmd -D KUBE-EXTERNAL-SERVICES $num ($line)"
        $cmd -D KUBE-EXTERNAL-SERVICES "$num" 2>/dev/null || true
      fi
    done < <($cmd -L KUBE-EXTERNAL-SERVICES -n --line-numbers 2>/dev/null | awk 'NR>2 {print}' | tac)
  fi
}
remove_kube_rejects iptables
remove_kube_rejects ip6tables

if command -v nft >/dev/null 2>&1 && [[ -n "${HOST_IP:-}" ]]; then
  echo "  reject kube restants (nft) :"
  nft list ruleset 2>/dev/null | grep -E "ip daddr ${HOST_IP}.*(tcp|udp) dport (80|443|53).*reject" \
    || echo "  (aucun match grep — OK si déjà nettoyé)"
fi

echo "[6] iptables INPUT (accepter 80/443/53 en tête, avant chaînes KUBE)"
accept_ports_input() {
  local proto="$1"
  command -v "$proto" >/dev/null 2>&1 || return 0
  for port in 80 443; do
    while $proto -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; do
      $proto -D INPUT -p tcp --dport "$port" -j ACCEPT || break
    done
  done
  for port in 53; do
    while $proto -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; do
      $proto -D INPUT -p tcp --dport "$port" -j ACCEPT || break
    done
    while $proto -C INPUT -p udp --dport "$port" -j ACCEPT 2>/dev/null; do
      $proto -D INPUT -p udp --dport "$port" -j ACCEPT || break
    done
  done
  if $proto -C INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null \
     || $proto -C INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; then
    $proto -I INPUT 2 -p tcp --dport 443 -j ACCEPT
    $proto -I INPUT 3 -p tcp --dport 80 -j ACCEPT
    $proto -I INPUT 4 -p udp --dport 53 -j ACCEPT
    $proto -I INPUT 5 -p tcp --dport 53 -j ACCEPT
  else
    $proto -I INPUT 1 -p tcp --dport 443 -j ACCEPT
    $proto -I INPUT 1 -p tcp --dport 80 -j ACCEPT
    $proto -I INPUT 1 -p udp --dport 53 -j ACCEPT
    $proto -I INPUT 1 -p tcp --dport 53 -j ACCEPT
    $proto -I INPUT 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
  fi
  echo "  $proto: ACCEPT tcp/80,443 + udp/tcp/53 avant KUBE-*"
}
accept_ports_input iptables
accept_ports_input ip6tables

echo "[7] nginx + named up"
systemctl enable --now nginx 2>/dev/null || true
systemctl restart nginx 2>/dev/null || true
systemctl enable --now named 2>/dev/null || systemctl enable --now bind9 2>/dev/null || true
systemctl restart named 2>/dev/null || systemctl restart bind9 2>/dev/null || true

echo "[8] Vérif reject encore présents ?"
if command -v nft >/dev/null 2>&1 && [[ -n "${HOST_IP:-}" ]]; then
  if nft list ruleset 2>/dev/null | grep -E "ip daddr ${HOST_IP}.*(tcp|udp) dport (80|443|53).*reject"; then
    echo "  [!] REJECT encore là — redémarrage k3s…"
    systemctl restart k3s 2>/dev/null || true
    sleep 8
    accept_ports_input iptables
    accept_ports_input ip6tables
    systemctl restart nginx 2>/dev/null || true
    systemctl restart named 2>/dev/null || systemctl restart bind9 2>/dev/null || true
    echo "  après restart k3s :"
    nft list ruleset 2>/dev/null | grep -E "ip daddr ${HOST_IP}.*(tcp|udp) dport (80|443|53).*reject" \
      && echo "  [!] REJECT persiste — voir kubectl get svc -A" \
      || echo "  OK : plus de REJECT sur ${HOST_IP}:80/443/53"
  else
    echo "  OK : pas de REJECT nft sur ${HOST_IP}:80/443/53"
  fi
fi

echo "[9] Tests"
echo "  local http : $(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1/login || echo fail)"
if [[ -n "$HOST_IP" ]]; then
  echo "  via IP ($HOST_IP) : $(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 "http://${HOST_IP}/login" 2>/dev/null || echo fail)"
  if command -v dig >/dev/null 2>&1; then
    echo "  dig @$HOST_IP 7une.info A : $(dig @"$HOST_IP" 7une.info A +short +time=2 +tries=1 2>/dev/null || echo '(timeout/vide — lancer ensure-dns.sh)')"
  fi
fi
if command -v kubectl >/dev/null 2>&1; then
  echo "  LoadBalancer restants :"
  kubectl get svc -A --field-selector spec.type=LoadBalancer 2>/dev/null || true
fi

echo
echo "=== Suite ==="
echo "1) Depuis VOTRE PC : https://${HOST_IP}/login"
echo "2) Pare-feu Contabo : ouvrir TCP 80, 443 et UDP/TCP 53."
echo "3) DNS : dig @${HOST_IP} votredomaine.com A +short"
echo "4) Puis réessayer Let's Encrypt dans le panel."
