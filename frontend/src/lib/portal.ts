/** Portail lié au port nginx (Admin 9086 / Client 9082 / hostname partagé). */

export type PortalKind = "admin" | "client" | "shared" | "webmail";

let cachedPortal: PortalKind | null = null;

export function detectPortalSync(): PortalKind {
  const p = window.location.port;
  if (p === "9086" || p === "9443") return "admin";
  if (p === "9082" || p === "8443") return "client";
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
  if (portal === "admin") return role === "administrator" || role === "reseller";
  if (portal === "client") return role === "client";
  return true;
}

export function homePathFor(
  role: string | undefined,
  portal: PortalKind = detectPortalSync(),
): string {
  if (portal === "admin") return "/whm";
  if (portal === "client") return "/panel";
  if (role === "client") return "/panel";
  return "/whm";
}

export function portalLabel(portal: PortalKind = detectPortalSync()): string {
  if (portal === "admin") return "Admin";
  if (portal === "client") return "Espace client";
  return "Panel";
}
