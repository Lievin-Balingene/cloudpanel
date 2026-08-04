#!/usr/bin/env bash
# Ouvre HTTP/HTTPS depuis l'extérieur (timeout navigateur / ERR_CONNECTION_TIMED_OUT).
# Causes fréquentes : UFW, firewalld, règles REJECT kube-proxy (LoadBalancer k3s), Contabo.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo "=== repair-external-access (ports 80/443) ==="

echo "[1] Écoute locale"
ss -tlnp | grep -E ':80\s|:443\s' || true

echo "[2] UFW"
if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH || ufw allow 22/tcp || true
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
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
    # Supprimer tout Service type LoadBalancer (souvent Traefik → REJECT sur IP publique:80/443)
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

echo "[5] Supprimer les REJECT kube-proxy sur ${HOST_IP:-host}:80/443"
# Ces règles provoquent connexion refusée / timeouts pour nginx sur l'IP publique.
remove_kube_rejects() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || return 0
  # Chaîne classique iptables-legacy / iptables-nft
  if $cmd -L KUBE-EXTERNAL-SERVICES -n >/dev/null 2>&1; then
    # Lister et supprimer les règles reject sur dport 80/443 vers l'IP hôte
    local line
    while read -r line; do
      [[ -z "$line" ]] && continue
      # num rule...
      local num="${line%% *}"
      if echo "$line" | grep -qE "dpt:(80|443).*reject|reject.*dpt:(80|443)"; then
        echo "  $cmd -D KUBE-EXTERNAL-SERVICES $num ($line)"
        $cmd -D KUBE-EXTERNAL-SERVICES "$num" 2>/dev/null || true
      elif [[ -n "${HOST_IP:-}" ]] && echo "$line" | grep -q "$HOST_IP" && echo "$line" | grep -qE 'dpt:(80|443)'; then
        echo "  $cmd -D KUBE-EXTERNAL-SERVICES $num ($line)"
        $cmd -D KUBE-EXTERNAL-SERVICES "$num" 2>/dev/null || true
      fi
    done < <($cmd -L KUBE-EXTERNAL-SERVICES -n --line-numbers 2>/dev/null | awk 'NR>2 {print}' | tac)
  fi
}
remove_kube_rejects iptables
remove_kube_rejects ip6tables

# nft : supprimer les reject explicites vers l'IP publique:80/443 (recréés tant que le Service LB existe)
if command -v nft >/dev/null 2>&1 && [[ -n "${HOST_IP:-}" ]]; then
  echo "  reject kube restants (nft) :"
  nft list ruleset 2>/dev/null | grep -E "ip daddr ${HOST_IP}.*tcp dport (80|443).*reject" || echo "  (aucun match grep — OK si déjà nettoyé)"
fi

echo "[6] iptables INPUT (accepter 80/443 en tête, avant chaînes KUBE)"
for proto in iptables ip6tables; do
  command -v "$proto" >/dev/null 2>&1 || continue
  while $proto -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; do
    $proto -D INPUT -p tcp --dport 80 -j ACCEPT || break
  done
  while $proto -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null; do
    $proto -D INPUT -p tcp --dport 443 -j ACCEPT || break
  done
  # Après ESTABLISHED si présent, sinon tout en tête
  if $proto -C INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null \
     || $proto -C INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; then
    $proto -I INPUT 2 -p tcp --dport 443 -j ACCEPT
    $proto -I INPUT 3 -p tcp --dport 80 -j ACCEPT
  else
    $proto -I INPUT 1 -p tcp --dport 443 -j ACCEPT
    $proto -I INPUT 1 -p tcp --dport 80 -j ACCEPT
    $proto -I INPUT 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
  fi
  echo "  $proto: ACCEPT tcp/80 et tcp/443 avant KUBE-*"
done

echo "[7] nginx up"
systemctl enable --now nginx 2>/dev/null || true
systemctl restart nginx 2>/dev/null || true

echo "[8] Vérif reject encore présents ?"
if command -v nft >/dev/null 2>&1 && [[ -n "${HOST_IP:-}" ]]; then
  if nft list ruleset 2>/dev/null | grep -E "ip daddr ${HOST_IP}.*tcp dport (80|443).*reject"; then
    echo "  [!] REJECT encore là — redémarrage k3s pour reconstruire kube-proxy sans Services LB…"
    systemctl restart k3s 2>/dev/null || true
    sleep 8
    # Re-poser ACCEPT (k3s réordonne souvent INPUT)
    for proto in iptables ip6tables; do
      command -v "$proto" >/dev/null 2>&1 || continue
      while $proto -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; do
        $proto -D INPUT -p tcp --dport 80 -j ACCEPT || break
      done
      while $proto -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null; do
        $proto -D INPUT -p tcp --dport 443 -j ACCEPT || break
      done
      $proto -I INPUT 1 -p tcp --dport 443 -j ACCEPT
      $proto -I INPUT 1 -p tcp --dport 80 -j ACCEPT
      $proto -I INPUT 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
    done
    systemctl restart nginx 2>/dev/null || true
    echo "  après restart k3s :"
    nft list ruleset 2>/dev/null | grep -E "ip daddr ${HOST_IP}.*tcp dport (80|443).*reject" \
      && echo "  [!] REJECT persiste — voir kubectl get svc -A" \
      || echo "  OK : plus de REJECT sur ${HOST_IP}:80/443"
  else
    echo "  OK : pas de REJECT nft sur ${HOST_IP}:80/443"
  fi
fi

echo "[9] Tests"
echo "  local : $(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1/login || echo fail)"
if [[ -n "$HOST_IP" ]]; then
  echo "  via IP ($HOST_IP) : $(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 "http://${HOST_IP}/login" 2>/dev/null || echo fail)"
fi
if command -v kubectl >/dev/null 2>&1; then
  echo "  LoadBalancer restants :"
  kubectl get svc -A --field-selector spec.type=LoadBalancer 2>/dev/null || true
fi

echo
echo "=== Suite ==="
echo "1) Depuis VOTRE PC : https://${HOST_IP}/login"
echo "2) Si ERR_CONNECTION_TIMED_OUT (pas REFUSED) : pare-feu Contabo → ouvrir TCP 80 et 443."
echo "3) Diagnostic :"
echo "   nft list ruleset | grep -E '${HOST_IP}.*(80|443).*reject'"
echo "   kubectl get svc -A | grep -iE 'LoadBalancer|traefik'"
