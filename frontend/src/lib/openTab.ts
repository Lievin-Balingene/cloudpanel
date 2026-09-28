/** Ouvre une URL SSO de façon fiable après un appel API async (évite le bloqueur de popups). */

export function resolveAppUrl(raw: string): string {
  const value = (raw || "").trim();
  if (!value) return "";
  if (value.startsWith("http://") || value.startsWith("https://")) return value;
  const path = value.startsWith("/") ? value : `/${value}`;
  return `${window.location.origin}${path}`;
}

/** À appeler synchrone dans le onClick (geste utilisateur). */
export function openBlankTab(): Window | null {
  try {
    return window.open("about:blank", "_blank");
  } catch {
    return null;
  }
}

/** Navigue l’onglet pré-ouvert, sinon nouvel onglet, sinon navigation même onglet. */
export function navigateOpenedTab(win: Window | null, rawUrl: string): void {
  const url = resolveAppUrl(rawUrl);
  if (!url) return;

  if (win && !win.closed) {
    try {
      win.location.replace(url);
      win.focus();
      return;
    } catch {
      try {
        win.close();
      } catch {
        /* ignore */
      }
    }
  }

  const popup = window.open(url, "_blank");
  if (!popup) {
    window.location.assign(url);
  }
}

export function closeOpenedTab(win: Window | null): void {
  if (win && !win.closed) {
    try {
      win.close();
    } catch {
      /* ignore */
    }
  }
}
