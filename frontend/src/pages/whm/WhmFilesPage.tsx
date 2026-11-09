import { useEffect, useRef } from "react";
import { ExternalLink, FolderOpen } from "lucide-react";
import { openFileManagerTab } from "@/lib/fileManager";

/** Lanceur WHM → ouvre le FM dans un nouvel onglet (UX cPanel). */
export function WhmFilesPage() {
  const opened = useRef(false);

  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    openFileManagerTab("/whm");
  }, []);

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white p-6 text-center shadow-sm animate-fade-up dark:border-ink-700 dark:bg-ink-950 sm:p-8">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-50 text-cp-orange dark:bg-orange-950/40">
        <FolderOpen className="h-7 w-7" />
      </div>
      <h1 className="mt-4 text-lg font-semibold text-slate-800 dark:text-ink-50">
        File Manager
      </h1>
      <p className="mt-2 text-sm text-slate-500">
        Opens in a new tab with a full-screen file manager (cPanel-style).
      </p>
      <button
        type="button"
        className="whm-btn-create mt-5 inline-flex items-center gap-2"
        onClick={() => openFileManagerTab("/whm")}
      >
        <ExternalLink className="h-4 w-4" />
        Open File Manager
      </button>
      <p className="mt-3 text-xs text-slate-400">
        Allow pop-ups for this site if the tab does not open.
      </p>
    </div>
  );
}
