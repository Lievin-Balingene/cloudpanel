#!/usr/bin/env bash
# Débloquer SSH après harden (prohibit-password / fail2ban).
# À exécuter en root via console KVM IBM Cloud (pas via SSH).
#
# Usage:
#   sudo bash /opt/vzone-src/scripts/repair-ssh-access.sh
#   sudo bash /opt/vzone-src/scripts/repair-ssh-access.sh 196.250.116.218
#   ALLOW_ROOT_PASSWORD=1 sudo bash ...   # réactive temporairement MDP root
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis (console KVM)"; exit 1; }

UNBAN_IP="${1:-}"
DROPIN="/etc/ssh/sshd_config.d/99-angapanel-harden.conf"

echo "[repair-ssh] fail2ban / ufw"
if command -v fail2ban-client >/dev/null 2>&1; then
  fail2ban-client status sshd 2>/dev/null || true
  if [[ -n "$UNBAN_IP" ]]; then
    fail2ban-client set sshd unbanip "$UNBAN_IP" 2>/dev/null \
      || fail2ban-client unban "$UNBAN_IP" 2>/dev/null \
      || true
    echo "[repair-ssh] unban demandé: $UNBAN_IP"
  else
    # Vide tous les bans sshd
    BANNED="$(fail2ban-client status sshd 2>/dev/null | sed -n 's/.*Banned IP list:\s*//p' || true)"
    for ip in $BANNED; do
      fail2ban-client set sshd unbanip "$ip" 2>/dev/null || true
      echo "[repair-ssh] unban: $ip"
    done
  fi
fi
command -v ufw >/dev/null 2>&1 && ufw allow OpenSSH >/dev/null 2>&1 || ufw allow 22/tcp >/dev/null 2>&1 || true

echo "[repair-ssh] sshd drop-in"
mkdir -p /etc/ssh/sshd_config.d
if [[ "${ALLOW_ROOT_PASSWORD:-0}" == "1" ]]; then
  cat >"$DROPIN" <<'EOF'
# Temporaire — repair-ssh-access.sh (remettre prohibit-password après clé)
PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication yes
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
X11Forwarding no
MaxAuthTries 6
LoginGraceTime 60
EOF
  echo "[repair-ssh] PermitRootLogin yes + PasswordAuthentication yes"
else
  cat >"$DROPIN" <<'EOF'
# AngaPanel — root = clé uniquement ; comptes normaux = MDP OK
PermitRootLogin prohibit-password
PasswordAuthentication yes
PubkeyAuthentication yes
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
X11Forwarding no
MaxAuthTries 4
LoginGraceTime 30
EOF
  echo "[repair-ssh] PermitRootLogin prohibit-password (PasswordAuthentication yes)"
fi

sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || systemctl restart ssh

echo
echo "[repair-ssh] OK"
echo "  Admin panel : sudo cat /etc/vzone/admin-credentials.txt"
echo "  Ajoutez votre clé :  echo 'ssh-ed25519 AAAA…' >> /root/.ssh/authorized_keys"
echo "  Puis: ALLOW_ROOT_PASSWORD=0 sudo bash $0   # re-durcir root"
ss -lntp | grep -E ':22\b' || true
