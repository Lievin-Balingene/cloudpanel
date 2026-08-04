#!/usr/bin/env bash
# Installe kubectl (+ k3s optionnel) pour le module Kubernetes.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

ENV_FILE="${ENV_FILE:-/etc/vzone/vzone.env}"

echo "[vzone] Installation Kubernetes tools (kubectl)"

if ! command -v kubectl >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl apt-transport-https gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    chmod 644 /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /" > /etc/apt/sources.list.d/kubernetes.list
    chmod 644 /etc/apt/sources.list.d/kubernetes.list
    apt-get update -qq
    apt-get install -y -qq kubectl
  elif command -v dnf >/dev/null 2>&1; then
    cat >/etc/yum.repos.d/kubernetes.repo <<'EOF'
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.30/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.30/rpm/repodata/repomd.xml.key
EOF
    dnf install -y kubectl
  fi
fi

if [[ "${VZONE_INSTALL_K3S:-0}" == "1" ]] && ! systemctl is-active --quiet k3s 2>/dev/null; then
  curl -sfL https://get.k3s.io | sh -
  systemctl enable --now k3s || true
fi

if [[ -f "${ENV_FILE}" ]]; then
  grep -q '^VZONE_K8S_PROVISION_MODE=' "${ENV_FILE}" || echo "VZONE_K8S_PROVISION_MODE=auto" >> "${ENV_FILE}"
  grep -q '^VZONE_KUBECTL_BIN=' "${ENV_FILE}" || echo "VZONE_KUBECTL_BIN=kubectl" >> "${ENV_FILE}"
fi

kubectl version --client 2>/dev/null || true
echo "[vzone] Kubernetes tooling prêt"
