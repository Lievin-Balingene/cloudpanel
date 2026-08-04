#!/usr/bin/env bash
# Installe kubectl (+ k3s optionnel) pour le module Kubernetes.
# Fallback : binaire officiel si apt/dnf échoue (réseau / miroir).
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"
KUBECTL_TARGET="${VZONE_KUBECTL_TARGET:-/usr/local/bin/kubectl}"

echo "[vzone] Installation Kubernetes tools (kubectl)"

resolve_kubectl() {
  local p=""
  for p in \
    "$(command -v kubectl 2>/dev/null || true)" \
    /usr/local/bin/kubectl \
    /usr/bin/kubectl \
    /snap/bin/kubectl \
    /usr/local/bin/k3s
  do
    if [[ -n "${p}" && -x "${p}" ]]; then
      # k3s binary can act as kubectl via "k3s kubectl" — prefer real kubectl
      if [[ "$(basename "${p}")" == "k3s" ]]; then
        continue
      fi
      echo "${p}"
      return 0
    fi
  done
  return 1
}

install_via_apt() {
  command -v apt-get >/dev/null 2>&1 || return 1
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq || true
  apt-get install -y -qq ca-certificates curl apt-transport-https gnupg || return 1
  install -m 0755 -d /etc/apt/keyrings
  if curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.31/deb/Release.key \
    | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg 2>/dev/null; then
    chmod 644 /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.31/deb/ /" \
      > /etc/apt/sources.list.d/kubernetes.list
    chmod 644 /etc/apt/sources.list.d/kubernetes.list
    apt-get update -qq || return 1
    apt-get install -y -qq kubectl || return 1
    return 0
  fi
  return 1
}

install_via_dnf() {
  command -v dnf >/dev/null 2>&1 || return 1
  cat >/etc/yum.repos.d/kubernetes.repo <<'EOF'
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.31/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.31/rpm/repodata/repomd.xml.key
EOF
  dnf install -y kubectl || return 1
  return 0
}

install_static_binary() {
  command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || {
    echo "[vzone] curl/wget requis pour le fallback binaire kubectl" >&2
    return 1
  }
  local arch ver url tmp
  case "$(uname -m)" in
    x86_64|amd64) arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    armv7l) arch="arm" ;;
    *)
      echo "[vzone] Architecture non supportée pour kubectl statique: $(uname -m)" >&2
      return 1
      ;;
  esac
  ver="$(curl -fsSL https://dl.k8s.io/release/stable.txt 2>/dev/null || true)"
  if [[ -z "${ver}" ]] && command -v wget >/dev/null 2>&1; then
    ver="$(wget -qO- https://dl.k8s.io/release/stable.txt 2>/dev/null || true)"
  fi
  ver="${ver:-v1.31.4}"
  url="https://dl.k8s.io/release/${ver}/bin/linux/${arch}/kubectl"
  tmp="$(mktemp)"
  echo "[vzone] Téléchargement kubectl ${ver} (${arch})…"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "${tmp}" "${url}" || { rm -f "${tmp}"; return 1; }
  else
    wget -qO "${tmp}" "${url}" || { rm -f "${tmp}"; return 1; }
  fi
  install -m 0755 "${tmp}" "${KUBECTL_TARGET}"
  rm -f "${tmp}"
  hash -r 2>/dev/null || true
  [[ -x "${KUBECTL_TARGET}" ]]
}

if ! resolve_kubectl >/dev/null; then
  installed=0
  if install_via_apt; then
    installed=1
  elif install_via_dnf; then
    installed=1
  elif install_static_binary; then
    installed=1
  fi
  if [[ "${installed}" -ne 1 ]]; then
    echo "[vzone] ÉCHEC: impossible d'installer kubectl (apt/dnf/binaire)." >&2
    exit 1
  fi
fi

# Si kubectl n'est toujours pas dans le PATH mais le binaire cible existe
if ! resolve_kubectl >/dev/null && [[ -x "${KUBECTL_TARGET}" ]]; then
  :
fi

if [[ "${VZONE_INSTALL_K3S:-0}" == "1" ]] && ! systemctl is-active --quiet k3s 2>/dev/null; then
  # IMPORTANT : ne pas laisser Traefik/ServiceLB prendre les ports 80/443 (réservés à nginx panel).
  mkdir -p /etc/rancher/k3s
  cat > /etc/rancher/k3s/config.yaml <<'EOF'
# V-zone Panel : nginx conserve 80/443 pour le panel et les vhosts.
disable:
  - traefik
  - servicelb
EOF
  curl -sfL https://get.k3s.io | sh -
  systemctl enable --now k3s || true
fi

# Rendre le kubeconfig k3s lisible par l'utilisateur panel (vzone)
if [[ -f /etc/rancher/k3s/k3s.yaml ]]; then
  install -d -m 750 -o root -g vzone /etc/vzone 2>/dev/null || install -d -m 755 /etc/vzone
  # Remplace 127.0.0.1 par localhost si besoin ; copie pour le user vzone
  sed 's#https://127.0.0.1:#https://127.0.0.1:#g' /etc/rancher/k3s/k3s.yaml > /etc/vzone/kubeconfig
  chown root:vzone /etc/vzone/kubeconfig
  chmod 640 /etc/vzone/kubeconfig
  if [[ -f "${ENV_FILE}" ]]; then
    if grep -q '^KUBECONFIG=' "${ENV_FILE}"; then
      sed -i 's|^KUBECONFIG=.*|KUBECONFIG=/etc/vzone/kubeconfig|' "${ENV_FILE}"
    else
      echo "KUBECONFIG=/etc/vzone/kubeconfig" >> "${ENV_FILE}"
    fi
  fi
  echo "[vzone] kubeconfig panel: /etc/vzone/kubeconfig"
fi

KUBECTL_PATH="$(resolve_kubectl || true)"
if [[ -z "${KUBECTL_PATH}" ]]; then
  echo "[vzone] ÉCHEC: kubectl introuvable après installation." >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  grep -q '^VZONE_K8S_PROVISION_MODE=' "${ENV_FILE}" || echo "VZONE_K8S_PROVISION_MODE=auto" >> "${ENV_FILE}"
  if grep -q '^VZONE_KUBECTL_BIN=' "${ENV_FILE}"; then
    sed -i "s|^VZONE_KUBECTL_BIN=.*|VZONE_KUBECTL_BIN=${KUBECTL_PATH}|" "${ENV_FILE}"
  else
    echo "VZONE_KUBECTL_BIN=${KUBECTL_PATH}" >> "${ENV_FILE}"
  fi
fi

"${KUBECTL_PATH}" version --client 2>/dev/null || true
echo "[vzone] kubectl OK: ${KUBECTL_PATH}"

# Recharger l'API pour prendre VZONE_KUBECTL_BIN (EnvironmentFile systemd)
if systemctl list-unit-files vzone-api.service >/dev/null 2>&1; then
  systemctl daemon-reload 2>/dev/null || true
  systemctl restart vzone-api.service 2>/dev/null || true
  echo "[vzone] vzone-api redémarré pour charger VZONE_KUBECTL_BIN"
fi

echo "[vzone] Kubernetes tooling prêt"
