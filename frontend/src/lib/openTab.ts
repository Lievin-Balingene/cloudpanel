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
 * Navigue l’onglet pré-ouvert EXACTEMENT une fois.
 * (meta refresh + location.replace = double hit → token SSO consommé 2×)
 */
export function navigateOpenedTab(win: Window | null, rawUrl: string): void {
  const url = resolveAppUrl(rawUrl);
  if (!url) return;

  if (win && !win.closed) {
    try {
      // Empêche un éventuel prefetch / historique de rejouer le GET SSO
      const sep = url.includes("?") ? "&" : "?";
      const once = `${url}${sep}_=${Date.now().toString(36)}`;
      win.location.replace(once);
      try {
        win.focus();
      } catch {
        /* ignore */
      }
      return;
    } catch {
      try {
        win.document.open();
        win.document.write(
          `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Webmail</title>` +
            `<meta http-equiv="Cache-Control" content="no-store">` +
            `</head><body><p>Ouverture du webmail…</p>` +
            `<script>location.replace(${JSON.stringify(url)});</script></body></html>`,
        );
        win.document.close();
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

  // Dernier recours : même onglet (jamais bloqué par le popup blocker)
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
