/** Portail lié au port nginx (Admin 9086 / Client 9082 / hostname partagé). */

export type PortalKind = "admin" | "client" | "shared" | "webmail";

const ADMIN_PORTS = new Set(["9086", "9443"]);
const CLIENT_PORTS = new Set(["9082", "8443"]);

let cachedPortal: PortalKind | null = null;

export function detectPortalSync(): PortalKind {
  const p = window.location.port;
  if (ADMIN_PORTS.has(p)) return "admin";
  if (CLIENT_PORTS.has(p)) return "client";
  if (p === "9095") return "webmail";
  return "shared";
}

export async function resolvePortal(): Promise<PortalKind> {
  if (cachedPortal) return cachedPortal;
  try {
    const res = await fetch("/portal.json", { cache: "no-store" });
    if (res.ok) {
      const data = (await res.json()) as { portal?: string };
      const portal = String(data.portal || "").toLowerCase();
      if (
        portal === "admin" ||
        portal === "client" ||
        portal === "shared" ||
        portal === "webmail"
      ) {
        cachedPortal = portal;
        return cachedPortal;
      }
    }
  } catch {
    /* fallback sync */
  }
  cachedPortal = detectPortalSync();
  return cachedPortal;
}

export function roleAllowedOnPortal(
  role: string | undefined,
  portal: PortalKind = detectPortalSync(),
): boolean {
  if (!role || portal === "shared" || portal === "webmail") return true;
  // Admin (WHM) : administrator + reseller
  if (portal === "admin") return role === "administrator" || role === "reseller";
  // V-zone Panel : client + reseller (le revendeur a aussi son panel client)
  if (portal === "client") return role === "client" || role === "reseller";
  return true;
}

export function homePathFor(
  role: string | undefined,
  portal: PortalKind = detectPortalSync(),
): string {
  if (portal === "admin") return "/whm";
  if (portal === "client") return "/panel";
  if (role === "client") return "/panel";
  // Shared hostname : reseller → Admin par défaut (peut ouvrir V-zone Panel via le lien)
  return "/whm";
}

export function portalLabel(portal: PortalKind = detectPortalSync()): string {
  if (portal === "admin") return "V-zone Admin";
  if (portal === "client") return "V-zone Panel";
  return "V-zone";
}

/** URL vers V-zone Admin / WHM (port Admin) — depuis le V-zone Panel du revendeur. */
export function whmPortalUrl(path = "/whm"): string {
  const { protocol, hostname } = window.location;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${protocol}//${hostname}:9086${p}`;
}

/** URL vers V-zone Panel (port Client) — depuis V-zone Admin / WHM. */
export function cpanelPortalUrl(path = "/panel"): string {
  const { protocol, hostname } = window.location;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${protocol}//${hostname}:9082${p}`;
}
