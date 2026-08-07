#!/usr/bin/env bash
# Crée /home/<user> (arbre cPanel) en root — appelé via sudo depuis le panel.
# Usage: vzone-mkhome <username>
set -euo pipefail

USERNAME="${1:-}"
HOME_ROOT="${VZONE_HOME_ROOT:-/home}"
VZONE_USER="${VZONE_USER:-vzone}"
CLIENTS_GROUP="${VZONE_CLIENTS_GROUP:-vzone-clients}"

if [[ ${EUID:-0} -ne 0 ]]; then
  echo "root requis" >&2
  exit 1
fi

if [[ ! "$USERNAME" =~ ^[a-z][a-z0-9_-]{2,31}$ ]]; then
  echo "username invalide: ${USERNAME}" >&2
  exit 2
fi

case "$USERNAME" in
  root|vzone|vmail|nobody|www|www-data|admin|mysql|postgres|ftp|mail) echo "username réservé" >&2; exit 2 ;;
esac

# Empêche path traversal
HOME_DIR="$(realpath -m "${HOME_ROOT}/${USERNAME}")"
case "$HOME_DIR" in
  "${HOME_ROOT}"/"${USERNAME}") ;;
  *) echo "chemin home invalide" >&2; exit 2 ;;
esac

mkdir -p "${HOME_ROOT}"
# Panel doit pouvoir créer d'autres homes ensuite
if command -v setfacl >/dev/null 2>&1; then
  setfacl -m "u:${VZONE_USER}:rwx" "${HOME_ROOT}" 2>/dev/null || true
  setfacl -d -m "u:${VZONE_USER}:rwx" "${HOME_ROOT}" 2>/dev/null || true
else
  chown "root:${VZONE_USER}" "${HOME_ROOT}" 2>/dev/null || true
  chmod 2775 "${HOME_ROOT}" 2>/dev/null || true
fi

groupadd --system "${CLIENTS_GROUP}" 2>/dev/null || true

mkdir -p \
  "${HOME_DIR}"/{public_html/cgi-bin,public_html/.well-known,private_html,public_ftp,mail,tmp,logs,etc,ssl/{certs,keys,csrs},domains,.trash,.htpasswds,.spamassassin,.cpanel}

[[ -e "${HOME_DIR}/www" ]] || ln -sfn public_html "${HOME_DIR}/www"
[[ -e "${HOME_DIR}/access-logs" ]] || ln -sfn logs "${HOME_DIR}/access-logs"

chmod 755 "${HOME_DIR}" "${HOME_DIR}/public_html" 2>/dev/null || true

# Compte OS pour cron/terminal (sans -m : home déjà créé)
if ! id -u "${USERNAME}" >/dev/null 2>&1; then
  useradd -M -d "${HOME_DIR}" -s /bin/bash -g "${CLIENTS_GROUP}" "${USERNAME}" 2>/dev/null \
    || useradd -M -d "${HOME_DIR}" -s /bin/bash "${USERNAME}" || true
fi

# Obligatoire pour sudoers terminal : vzone ALL=(%vzone-clients) ...
if id -u "${USERNAME}" >/dev/null 2>&1; then
  if ! id -nG "${USERNAME}" 2>/dev/null | tr ' ' '\n' | grep -qx "${CLIENTS_GROUP}"; then
    usermod -aG "${CLIENTS_GROUP}" "${USERNAME}" 2>/dev/null || true
  fi
fi

# Propriétaire = compte OS si possible, sinon vzone ; ACL panel toujours
if id -u "${USERNAME}" >/dev/null 2>&1; then
  chown -R "${USERNAME}:${CLIENTS_GROUP}" "${HOME_DIR}" 2>/dev/null \
    || chown -R "${USERNAME}:${USERNAME}" "${HOME_DIR}" 2>/dev/null || true
else
  chown -R "${VZONE_USER}:${VZONE_USER}" "${HOME_DIR}" 2>/dev/null || true
fi

if command -v setfacl >/dev/null 2>&1; then
  setfacl -R -m "u:${VZONE_USER}:rwx" "${HOME_DIR}" 2>/dev/null || true
  setfacl -R -d -m "u:${VZONE_USER}:rwx" "${HOME_DIR}" 2>/dev/null || true
fi

chmod 755 "${HOME_DIR}" "${HOME_DIR}/public_html" 2>/dev/null || true
echo "OK ${HOME_DIR}"
