#!/usr/bin/env bash
# Installe BIND9 en mode autoritaire uniquement et branche les zones V-zone.
# Important: libère le port 53 (systemd-resolved stub) sinon named n'écoute pas en public.
set -euo pipefail

[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VZONE_ROOT="${VZONE_ROOT:-/opt/vzone}"
NAMED_DIR="${VZONE_DNS_DIR:-/var/lib/vzone/named}"
ZONES_DIR="${NAMED_DIR}/zones"
ZONES_CONF="${NAMED_DIR}/zones.conf"

echo "[vzone-dns] Installation BIND9 (autoritaire)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq bind9 bind9-utils dnsutils || apt-get install -y bind9 bind9utils dnsutils

mkdir -p "${ZONES_DIR}"
touch "${ZONES_CONF}"
chmod 755 "${NAMED_DIR}" "${ZONES_DIR}"
chmod 644 "${ZONES_CONF}"

# --- Port 53 : désactiver le stub systemd-resolved (127.0.0.53) ---
# Sans ça, named ne peut pas binder 0.0.0.0:53 et Google DNS timeoute.
echo "[vzone-dns] Libération du port 53 (DNSStubListener=no)"
mkdir -p /etc/systemd/resolved.conf.d
cat > /etc/systemd/resolved.conf.d/vzone-dns.conf <<'EOF'
[Resolve]
DNS=1.1.1.1 8.8.8.8
FallbackDNS=9.9.9.9
DNSStubListener=no
EOF
# resolv.conf pour le serveur lui-même (plus 127.0.0.53)
if [[ -f /run/systemd/resolve/resolv.conf ]]; then
  ln -sfn /run/systemd/resolve/resolv.conf /etc/resolv.conf
elif [[ ! -e /etc/resolv.conf ]] || grep -q '127.0.0.53' /etc/resolv.conf 2>/dev/null; then
  printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' > /etc/resolv.conf
fi
systemctl restart systemd-resolved 2>/dev/null || true
sleep 1

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
    dnssec-validation no;
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

# AppArmor : autoriser lecture des zones V-zone
if [[ -d /etc/apparmor.d/local ]]; then
  mkdir -p /etc/apparmor.d/local
  cat > /etc/apparmor.d/local/usr.sbin.named <<EOF
# V-zone DNS zones
${NAMED_DIR}/** r,
${ZONES_DIR}/** rw,
EOF
  if command -v apparmor_parser >/dev/null 2>&1; then
    apparmor_parser -r /etc/apparmor.d/usr.sbin.named 2>/dev/null || true
  fi
  systemctl reload apparmor 2>/dev/null || true
fi

# Helper reload (rndc)
install -m 755 "${REPO_DIR}/scripts/vzone-named-reload.sh" /usr/local/sbin/vzone-named-reload
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-named-reload.service" /etc/systemd/system/vzone-named-reload.service
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-named-reload.path" /etc/systemd/system/vzone-named-reload.path

# Santé DNS périodique (anti-SERVFAIL)
install -m 755 "${REPO_DIR}/scripts/vzone-dns-health.sh" /usr/local/sbin/vzone-dns-health
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-dns-health.service" /etc/systemd/system/vzone-dns-health.service
install -m 644 "${REPO_DIR}/deploy/systemd/vzone-dns-health.timer" /etc/systemd/system/vzone-dns-health.timer

systemctl daemon-reload
systemctl enable named 2>/dev/null || systemctl enable bind9 2>/dev/null || true
systemctl enable --now vzone-named-reload.path
systemctl enable --now vzone-dns-health.timer

# Firewall DNS
if command -v ufw >/dev/null 2>&1; then
  ufw allow 53/tcp || true
  ufw allow 53/udp || true
elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
  firewall-cmd --permanent --add-service=dns || true
  firewall-cmd --reload || true
fi

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
for proto in iptables ip6tables; do
  command -v "$proto" >/dev/null 2>&1 || continue
  $proto -I INPUT 1 -p udp --dport 53 -j ACCEPT 2>/dev/null || true
  $proto -I INPUT 1 -p tcp --dport 53 -j ACCEPT 2>/dev/null || true
done

# --- Sync code DNS depuis git → runtime (/opt/vzone) si besoin ---
# (git pull seul dans /opt/vzone-src ne met pas à jour manage.py de production)
if [[ -d "${REPO_DIR}/backend/apps/dns" && -d "${VZONE_ROOT}/backend/apps" ]]; then
  echo "[vzone-dns] Synchronisation apps/dns → ${VZONE_ROOT}"
  mkdir -p "${VZONE_ROOT}/backend/apps/dns/management/commands"
  rsync -a \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    "${REPO_DIR}/backend/apps/dns/" "${VZONE_ROOT}/backend/apps/dns/"
  # settings paths DNS
  if [[ -f "${REPO_DIR}/backend/vzone/settings/base.py" ]]; then
    rsync -a "${REPO_DIR}/backend/vzone/settings/base.py" "${VZONE_ROOT}/backend/vzone/settings/base.py"
  fi
fi

# Exporter les zones depuis Django
sync_ok=0
if [[ -x "${VZONE_ROOT}/backend/.venv/bin/python" && -f /etc/vzone/vzone.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/vzone/vzone.env
  set +a
  export DJANGO_SETTINGS_MODULE=vzone.settings.production
  export VZONE_DNS_ZONES_DIR="${ZONES_DIR}"
  export VZONE_DNS_ZONES_CONF="${ZONES_CONF}"
  export VZONE_DNS_RELOAD_FLAG="${NAMED_DIR}/reload.requested"
  if "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" sync_dns_zones; then
    sync_ok=1
    "${VZONE_ROOT}/backend/.venv/bin/python" "${VZONE_ROOT}/backend/manage.py" check_dns_zones --disk-files \
      || echo "[vzone-dns] ALERTE: check_dns_zones a signalé des problèmes"
  else
    echo "[vzone-dns] ERREUR: sync_dns_zones a échoué — lancez: sudo bash ${REPO_DIR}/scripts/update.sh"
  fi
else
  echo "[vzone-dns] Runtime ${VZONE_ROOT} incomplet — lancez update.sh"
fi

# Droits : bind lit, vzone écrit
if getent group bind >/dev/null; then
  chown -R vzone:bind "${NAMED_DIR}" 2>/dev/null || chown -R root:bind "${NAMED_DIR}"
  usermod -aG bind vzone 2>/dev/null || true
elif getent group named >/dev/null; then
  chown -R vzone:named "${NAMED_DIR}" 2>/dev/null || chown -R root:named "${NAMED_DIR}"
  usermod -aG named vzone 2>/dev/null || true
fi
chmod 775 "${NAMED_DIR}" "${ZONES_DIR}" || true
chmod -R g+rwX "${NAMED_DIR}" || true
# named doit pouvoir lire les .zone
find "${ZONES_DIR}" -type f -name '*.zone' -exec chmod 644 {} \; 2>/dev/null || true
chmod 644 "${ZONES_CONF}" || true

echo "[vzone-dns] named-checkzone (toutes les zones)"
check_fail=0
if command -v named-checkzone >/dev/null 2>&1; then
  shopt -s nullglob
  for zf in "${ZONES_DIR}"/*.zone; do
    zname="$(basename "${zf}" .zone)"
    if ! named-checkzone "${zname}" "${zf}" >/tmp/vzone-checkzone.out 2>&1; then
      echo "[vzone-dns] ERREUR zone ${zname}:" >&2
      head -n 20 /tmp/vzone-checkzone.out >&2 || true
      check_fail=1
    else
      echo "[vzone-dns] OK ${zname}"
    fi
  done
  shopt -u nullglob
else
  echo "[vzone-dns] named-checkzone absent — skip"
fi

echo "[vzone-dns] named-checkconf"
if ! named-checkconf; then
  echo "[vzone-dns] ERREUR named-checkconf" >&2
  named-checkconf -z 2>&1 | head -n 40 || true
fi

systemctl restart named 2>/dev/null || systemctl restart bind9 2>/dev/null || true
sleep 1

echo "[vzone-dns] statut named:"
systemctl is-active named 2>/dev/null || systemctl is-active bind9 2>/dev/null || true
systemctl --no-pager -l status named 2>/dev/null | head -n 20 || \
  systemctl --no-pager -l status bind9 2>/dev/null | head -n 20 || true

if [[ "${check_fail}" -ne 0 ]]; then
  echo "[vzone-dns] ALERTE: au moins une zone invalide (SERVFAIL public)" >&2
  journalctl -u named -u bind9 -n 30 --no-pager 2>/dev/null || true
fi

echo "[vzone-dns] écoute :53"
ss -ulnp | grep ':53' || true
ss -tlnp | grep ':53' || true

if ! ss -ulnp 2>/dev/null | grep -qE '0\.0\.0\.0:53|\[::\]:53|\*:53'; then
  if ! ss -ulnp 2>/dev/null | grep -v '127.0.0.53' | grep -q ':53'; then
    echo "[vzone-dns] ALERTE: named n'écoute PAS sur 0.0.0.0:53" >&2
    journalctl -u named -u bind9 -n 40 --no-pager 2>/dev/null || true
  fi
fi

echo "[vzone-dns] Zones exportées:"
ls -la "${ZONES_DIR}" 2>/dev/null | head -n 30 || true
echo "--- zones.conf ---"
head -n 40 "${ZONES_CONF}" 2>/dev/null || true

if [[ -n "${HOST_IP}" ]] && command -v dig >/dev/null 2>&1; then
  echo "[vzone-dns] Tests locaux"
  dig @"${HOST_IP}" 7une.info A +short +time=2 +tries=1 || true
  dig @127.0.0.1 7une.info A +short +time=2 +tries=1 || true
fi

echo "[vzone-dns] BIND9 prêt — zones dans ${ZONES_DIR} (sync_ok=${sync_ok})"
echo "[vzone-dns] Vérif publique: dig @${HOST_IP:-IP} 7une.info A +short"
echo "[vzone-dns] Contabo: ouvrir UDP/TCP 53 si dig public timeout encore"
