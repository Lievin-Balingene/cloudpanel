"""ACL revendeur style cPanel — catalogue de privileges + helpers."""
from __future__ import annotations

from typing import Iterable

# Codename → libellé (groupes comme Edit Reseller Privileges cPanel)
PRIVILEGE_CATALOG: dict[str, list[tuple[str, str]]] = {
    "Account Functions": [
        ("create-acct", "Create Accounts"),
        ("create-reseller", "Create Reseller Accounts (root only)"),
        ("kill-acct", "Terminate Accounts"),
        ("suspend-acct", "Suspend / Unsuspend Accounts"),
        ("list-accts", "List Accounts"),
        ("edit-account", "Edit Account"),
        ("upgrade-account", "Change Account Package"),
        ("view-account-bandwidth", "View Bandwidth Usage"),
    ],
    "Packages": [
        ("list-pkgs", "List Packages"),
        ("create-pkgs", "Add Packages"),
        ("edit-pkgs", "Edit Packages"),
        ("delete-pkgs", "Delete Packages"),
    ],
    "Domains & DNS": [
        ("manage-domains", "Manage Domains / SSL"),
        ("manage-dns", "DNS Zone Editor"),
    ],
    "Services": [
        ("manage-email", "Email Accounts"),
        ("manage-databases", "MySQL / PostgreSQL"),
        ("manage-ftp", "FTP Accounts"),
        ("manage-cron", "Cron Jobs"),
        ("manage-files", "File Manager"),
        ("manage-backups", "Backups"),
    ],
    "Software": [
        ("manage-python", "Setup Python App"),
        ("manage-node", "Setup Node.js App"),
        ("manage-php", "MultiPHP Manager"),
        ("manage-wordpress", "WordPress"),
        ("manage-git", "Git Version Control"),
        ("manage-docker", "Docker"),
    ],
    "Server (root only by default)": [
        ("edit-reseller-acls", "Edit Reseller Privileges"),
        ("res-server-setup", "Basic Server Setup"),
        ("res-transfer", "Transfer Tool"),
        ("res-ols", "OpenLiteSpeed"),
        ("res-terminal", "Server Terminal"),
        ("res-kubernetes", "Kubernetes"),
        ("res-panel-update", "Panel Update"),
        ("res-repairs", "Repairs"),
        ("res-monitoring", "Service Status / Monitoring"),
        ("res-resources", "Server Information"),
        ("res-firewall", "Firewall / Fail2Ban"),
        ("res-security", "Security Center"),
    ],
}

ALL_PRIVILEGE_CODES: frozenset[str] = frozenset(
    code for group in PRIVILEGE_CATALOG.values() for code, _ in group
)

# Privileges accordes par defaut a un nouveau revendeur (proche cPanel standard)
DEFAULT_RESELLER_PRIVILEGES: frozenset[str] = frozenset(
    {
        "create-acct",
        "kill-acct",
        "suspend-acct",
        "list-accts",
        "edit-account",
        "upgrade-account",
        "view-account-bandwidth",
        "list-pkgs",
        "create-pkgs",
        "edit-pkgs",
        "delete-pkgs",
        "manage-domains",
        "manage-dns",
        "manage-email",
        "manage-databases",
        "manage-ftp",
        "manage-cron",
        "manage-files",
        "manage-backups",
        "manage-python",
        "manage-node",
        "manage-php",
        "manage-wordpress",
        "manage-git",
    }
)

# Mapping route WHM → privilege requis (home toujours autorise)
ROUTE_PRIVILEGE_MAP: dict[str, str] = {
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
    "/whm/account-security": "list-accts",  # 2FA perso
    "/whm/resellers": "edit-reseller-acls",
}


def catalog_as_list() -> list[dict]:
    return [
        {
            "group": group,
            "privileges": [{"code": code, "label": label} for code, label in items],
        }
        for group, items in PRIVILEGE_CATALOG.items()
    ]


def sanitize_privileges(codes: Iterable[str]) -> list[str]:
    """
    Nettoie la liste ACL.
    create-reseller n'est jamais stocke sur un revendeur (reserve root / admin).
    """
    cleaned = sorted(
        {
            c
            for c in codes
            if c in ALL_PRIVILEGE_CODES and c != "create-reseller"
        }
    )
    return cleaned


def default_privileges_for_package(*, can_create_packages: bool = True) -> list[str]:
    privs = set(DEFAULT_RESELLER_PRIVILEGES)
    if not can_create_packages:
        privs -= {"create-pkgs", "edit-pkgs", "delete-pkgs"}
    return sorted(privs)
