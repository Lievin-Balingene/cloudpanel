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

/**
 * Navigue l’onglet pré-ouvert.
 * Utilise document.write + meta refresh (fiable cross-origin about:blank),
 * sinon location, sinon navigation même onglet (toujours OK).
 */
export function navigateOpenedTab(win: Window | null, rawUrl: string): void {
  const url = resolveAppUrl(rawUrl);
  if (!url) return;

  if (win && !win.closed) {
    try {
      const safe = url.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
      win.document.open();
      win.document.write(
        `<!DOCTYPE html><html><head><meta charset="utf-8">` +
          `<meta http-equiv="refresh" content="0;url=${safe}">` +
          `<title>Connexion webmail…</title></head><body style="font-family:system-ui;padding:2rem">` +
          `<p>Connexion au webmail…</p>` +
          `<script>location.replace(${JSON.stringify(url)});</script>` +
          `</body></html>`,
      );
      win.document.close();
      try {
        win.focus();
      } catch {
        /* ignore */
      }
      return;
    } catch {
      try {
        win.location.href = url;
        return;
      } catch {
        try {
          win.close();
        } catch {
          /* ignore */
        }
      }
    }
  }

  // Dernier recours : même onglet (jamais bloqué)
  window.location.assign(url);
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
