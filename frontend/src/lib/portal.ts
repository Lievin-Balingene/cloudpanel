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
  // WHM : admin + reseller
  if (portal === "admin") return role === "administrator" || role === "reseller";
  // cPanel : client + reseller (comme cPanel — le revendeur a aussi son cPanel)
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
  // Shared hostname : reseller → WHM par défaut (peut ouvrir cPanel via le lien)
  return "/whm";
}

export function portalLabel(portal: PortalKind = detectPortalSync()): string {
  if (portal === "admin") return "WHM";
  if (portal === "client") return "cPanel";
  return "Panel";
}

/** URL vers WHM (port Admin) — pour le bouton « WHM » dans le cPanel du revendeur. */
export function whmPortalUrl(path = "/whm"): string {
  const { protocol, hostname } = window.location;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${protocol}//${hostname}:9086${p}`;
}

/** URL vers cPanel (port Client) — pour le bouton « cPanel » dans WHM. */
export function cpanelPortalUrl(path = "/panel"): string {
  const { protocol, hostname } = window.location;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${protocol}//${hostname}:9082${p}`;
}
