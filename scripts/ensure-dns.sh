#!/usr/bin/env bash
# Installe BIND9 en mode autoritaire uniquement et branche les zones V-zone.
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
NAMED_DIR="${VZONE_DNS_DIR:-/var/lib/vzone/named}"
ZONES_DIR="${NAMED_DIR}/zones"
ZONES_CONF="${NAMED_DIR}/zones.conf"
RELOAD_FLAG="${NAMED_DIR}/reload.requested"

echo "[vzone-dns] Installation BIND9 (autoritaire)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq bind9 bind9-utils dnsutils || apt-get install -y bind9 bind9utils dnsutils

mkdir -p "${ZONES_DIR}"
touch "${ZONES_CONF}"
chown -R bind:bind "${NAMED_DIR}" 2>/dev/null || chown -R named:named "${NAMED_DIR}" 2>/dev/null || true
chmod 755 "${NAMED_DIR}" "${ZONES_DIR}"
chmod 644 "${ZONES_CONF}"

# Conf principale : autoritaire only (pas de récursion ouverte)
OPTIONS_FILE="/etc/bind/named.conf.options"
if [[ -f "${OPTIONS_FILE}" ]]; then
  cp -a "${OPTIONS_FILE}" "${OPTIONS_FILE}.vzone-bak.$(date +%s)" || true
fi
cat > "${OPTIONS_FILE}" <<EOF
options {
    directory "/var/cache/bind";
    listen-on port 53 { any; };
    listen-on-v6 { any; };
    allow-query { any; };
    allow-recursion { none; };
    recursion no;
    allow-transfer { none; };
    dnssec-validation auto;
    auth-nxdomain no;
};
EOF

# Include zones V-zone
LOCAL_FILE="/etc/bind/named.conf.local"
touch "${LOCAL_FILE}"
if ! grep -q 'vzone/named/zones.conf' "${LOCAL_FILE}" 2>/dev/null; then
  cat >> "${LOCAL_FILE}" <<EOF

// V-zone hosted zones
include "${ZONES_CONF}";
EOF
fi

# Helper reload (rndc)
install -m 755 "${REPO_DIR}/scripts/vzone-named-reload.sh" /usr/local/sbin/vzone-named-reload
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-named-reload.service" /etc/systemd/system/vzone-named-reload.service
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-named-reload.path" /etc/systemd/system/vzone-named-reload.path

systemctl daemon-reload
systemctl enable named 2>/dev/null || systemctl enable bind9 2>/dev/null || true
systemctl restart named 2>/dev/null || systemctl restart bind9 2>/dev/null || true
systemctl enable --now vzone-named-reload.path

# Firewall DNS
if command -v ufw >/dev/null 2>&1; then
  ufw allow 53/tcp || true
  ufw allow 53/udp || true
elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
  firewall-cmd --permanent --add-service=dns || true
  firewall-cmd --reload || true
fi

# Exporter les zones depuis Django si dispo
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" && -f /etc/vzone/vzone.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/vzone/vzone.env
  set +a
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" sync_dns_zones || \
    echo "[vzone-dns] Avertissement: sync_dns_zones a échoué (zones vides ou DB down)"
fi

# Droits après sync (fichiers écrits par user vzone)
chown -R bind:bind "${NAMED_DIR}" 2>/dev/null || chown -R named:named "${NAMED_DIR}" 2>/dev/null || true
# L'API (user vzone) doit pouvoir réécrire les zones
chmod 775 "${ZONES_DIR}" "${NAMED_DIR}" || true
if getent group bind >/dev/null && id vzone >/dev/null 2>&1; then
  usermod -aG bind vzone 2>/dev/null || true
  chgrp -R bind "${NAMED_DIR}" 2>/dev/null || true
elif getent group named >/dev/null && id vzone >/dev/null 2>&1; then
  usermod -aG named vzone 2>/dev/null || true
  chgrp -R named "${NAMED_DIR}" 2>/dev/null || true
fi
chmod -R g+rwX "${NAMED_DIR}" || true

named-checkconf 2>/dev/null || true
systemctl restart named 2>/dev/null || systemctl restart bind9 2>/dev/null || true

echo "[vzone-dns] BIND9 prêt — zones dans ${ZONES_DIR}"
echo "[vzone-dns] Test: dig @127.0.0.1 VOTRE-DOMAINE A +short"
ss -ulnp 2>/dev/null | grep ':53' || ss -ulnp | head -n 5 || true
