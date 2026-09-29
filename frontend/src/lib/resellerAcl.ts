/** Mapping routes WHM → privilege ACL revendeur (miroir backend). */
export const ROUTE_PRIVILEGE_MAP: Record<string, string> = {
  "/whm/accounts/create": "create-acct",
  "/whm/accounts": "list-accts",
  "/whm/packages": "list-pkgs",
  "/whm/domains": "manage-domains",
  "/whm/dns": "manage-dns",
  "/whm/email": "manage-email",
  "/whm/databases": "manage-databases",
  "/whm/ftp": "manage-ftp",
  "/whm/cron": "manage-cron",
  "/whm/files": "manage-files",
  "/whm/files/upload": "manage-files",
  "/whm/files/edit": "manage-files",
  "/whm/backups": "manage-backups",
  "/whm/python": "manage-python",
  "/whm/node": "manage-node",
  "/whm/php": "manage-php",
  "/whm/wordpress": "manage-wordpress",
  "/whm/git": "manage-git",
  "/whm/docker": "manage-docker",
  "/whm/server-setup": "res-server-setup",
  "/whm/tweak-settings": "res-server-setup",
  "/whm/ip-functions": "res-firewall",
  "/whm/ai-ops": "res-terminal",
  "/whm/transfer": "res-transfer",
  "/whm/ols": "res-ols",
  "/whm/terminal": "res-terminal",
  "/whm/kubernetes": "res-kubernetes",
  "/whm/panel-update": "res-panel-update",
  "/whm/repairs": "res-repairs",
  "/whm/monitoring": "res-monitoring",
  "/whm/resources": "res-resources",
  "/whm/firewall": "res-firewall",
  "/whm/security": "res-security",
  "/whm/account-security": "list-accts",
  "/whm/resellers": "edit-reseller-acls",
};

/** Privilege root-only : jamais accordé à un revendeur. */
export const PRIV_CREATE_RESELLER = "create-reseller";

export function canAccessWhmRoute(
  role: string | undefined,
  privileges: string[] | undefined,
  path: string,
): boolean {
  if (role === "administrator") return true;
  if (role !== "reseller") return false;
  if (path === "/whm" || path === "/whm/") return true;
  const priv = ROUTE_PRIVILEGE_MAP[path];
  if (!priv) return false;
  return (privileges || []).includes(priv);
}

export function hasResellerPriv(
  role: string | undefined,
  privileges: string[] | undefined,
  code: string,
): boolean {
  // create-reseller : root uniquement, même si présent par erreur dans l'ACL
  if (code === PRIV_CREATE_RESELLER) {
    return role === "administrator";
  }
  if (role === "administrator") return true;
  if (role !== "reseller") return false;
  return (privileges || []).includes(code);
}

/** Peut créer un compte revendeur ? (UI Account Type) */
export function canCreateResellerAccount(
  role: string | undefined,
  _privileges?: string[] | undefined,
): boolean {
  return hasResellerPriv(role, _privileges, PRIV_CREATE_RESELLER);
}
