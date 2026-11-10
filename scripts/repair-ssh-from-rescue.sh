#!/usr/bin/env bash
# À exécuter depuis le Contabo Rescue System (SSH rescue marche).
# Monte le disque du VPS et répare sshd + clé root.
set -euo pipefail
[[ ${EUID:-0} -eq 0 ]] || { echo "Root requis"; exit 1; }

PUBKEY="${1:-ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDh/CJvtf1HLsCSbxQg+uwjhXAuNc7o3ZvYMvdR4vFb9 angapanel-recover}"
MNT="${MNT:-/mnt/vps}"
UNBAN_IP="${UNBAN_IP:-196.250.116.218}"

mkdir -p "$MNT"
# Trouver la partition root ( Contabo : souvent /dev/sda1 ou nvme0n1p1 )
ROOT_DEV=""
for cand in /dev/sda1 /dev/vda1 /dev/nvme0n1p1 /dev/sda2 /dev/vda2; do
  if [[ -b "$cand" ]] && mount "$cand" "$MNT" 2>/dev/null; then
    if [[ -d "$MNT/etc/ssh" ]]; then
      ROOT_DEV="$cand"
      break
    fi
    umount "$MNT" 2>/dev/null || true
  fi
done
if [[ -z "$ROOT_DEV" ]]; then
  echo "Partitions vues :"
  lsblk -f
  echo "Montez manuellement : mount /dev/XXX $MNT && relancez"
  exit 1
fi
echo "Monté $ROOT_DEV sur $MNT"

mkdir -p "$MNT/etc/ssh/sshd_config.d" "$MNT/root/.ssh"
cat >"$MNT/etc/ssh/sshd_config.d/99-angapanel-harden.conf" <<'EOF'
PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication yes
KbdInteractiveAuthentication no
EOF
chmod 700 "$MNT/root/.ssh"
touch "$MNT/root/.ssh/authorized_keys"
chmod 600 "$MNT/root/.ssh/authorized_keys"
if ! grep -qF "angapanel-recover" "$MNT/root/.ssh/authorized_keys" 2>/dev/null; then
  echo "$PUBKEY" >>"$MNT/root/.ssh/authorized_keys"
fi
chown -R root:root "$MNT/root/.ssh"

# Optionnel : script first-boot unban dans rc.local si présent
if [[ -d "$MNT/etc" ]]; then
  cat >"$MNT/tmp/angapanel-unban.sh" <<EOF
#!/bin/bash
fail2ban-client set sshd unbanip ${UNBAN_IP} 2>/dev/null || true
ufw allow OpenSSH 2>/dev/null || ufw allow 22/tcp 2>/dev/null || true
EOF
  chmod 755 "$MNT/tmp/angapanel-unban.sh" || true
fi

umount "$MNT"
echo
echo "OK — config SSH réparée sur le disque."
echo "Dans Contabo : désactivez Rescue System puis reboot normal."
echo "Ensuite : ssh -i ~/.ssh/angapanel_recover root@IP_PUBLIC"
