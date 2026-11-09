import { useEffect, useRef } from "react";
import { ExternalLink, FolderOpen } from "lucide-react";
import { openFileManagerTab } from "@/lib/fileManager";

/** Lanceur panel → ouvre le FM dans un nouvel onglet (UX cPanel). */
export function ClientFilesPage() {
  const opened = useRef(false);

  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    openFileManagerTab("/panel");
  }, []);

  return (
    <div className="vz-panel mx-auto max-w-lg animate-fade-up p-6 text-center sm:p-8">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-cp-orange/10 text-cp-orange">
        <FolderOpen className="h-7 w-7" />
      </div>
      <h1 className="mt-4 text-lg font-semibold text-cp-text">Gestionnaire de fichiers</h1>
      <p className="mt-2 text-sm text-cp-muted">
        Le gestionnaire s&apos;ouvre dans un nouvel onglet pour une vue plein écran, comme
        cPanel.
      </p>
      <button
        type="button"
        className="vz-btn-primary mt-5 inline-flex items-center gap-2"
        onClick={() => openFileManagerTab("/panel")}
      >
        <ExternalLink className="h-4 w-4" />
        Ouvrir le gestionnaire
      </button>
      <p className="mt-3 text-xs text-cp-muted">
        Si rien ne s&apos;affiche, autorisez les pop-ups pour ce site.
      </p>
    </div>
  );
}
