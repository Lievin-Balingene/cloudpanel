import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { ExternalLink, X } from "lucide-react";
import { BRAND } from "@/lib/brand";
import { resolvePanelBase } from "@/lib/fileUpload";

/** Shell plein écran style cPanel — File Manager seul dans l'onglet. */
export function FileManagerShell() {
  const location = useLocation();
  const panelBase = resolvePanelBase(location.pathname);
  const panelHome = panelBase === "/whm" ? "/whm" : "/panel";

  useEffect(() => {
    document.title = `Gestionnaire de fichiers · ${BRAND}`;
  }, []);

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-[#e8eef4] dark:bg-surface-dark">
      <header
        className="z-20 flex shrink-0 items-center justify-between gap-3 border-b border-[#c5d0dc] bg-[#1e3a55] px-3 py-2 text-white shadow-sm sm:px-4"
        style={{ paddingTop: "max(0.5rem, env(safe-area-inset-top))" }}
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <img
            src="/vzone-mark.svg"
            alt=""
            className="h-8 w-8 shrink-0 rounded-lg shadow-sm ring-1 ring-white/20"
            width={32}
            height={32}
          />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-wide">
              Gestionnaire de fichiers
            </p>
            <p className="truncate text-[10px] uppercase tracking-[0.14em] text-white/60">
              {BRAND}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <a
            href={panelHome}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-white/10 px-2.5 text-xs font-medium transition hover:bg-white/18"
            title="Retour au panneau"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Panneau</span>
          </a>
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 transition hover:bg-white/18"
            title="Fermer cet onglet"
            aria-label="Fermer"
            onClick={() => {
              if (window.opener && !window.opener.closed) {
                window.close();
                return;
              }
              window.location.href = panelHome;
            }}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </header>
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden p-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:p-3">
        <div className="flex min-h-0 flex-1 flex-col">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
