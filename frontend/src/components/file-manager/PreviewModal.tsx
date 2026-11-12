import { useEffect, useState } from "react";
import { X, Download, Loader2 } from "lucide-react";
import type { FileEntry } from "./types";

export function PreviewModal({
  entry,
  token,
  onClose,
  onDownload,
}: {
  entry: FileEntry;
  token: string | null;
  onClose: () => void;
  onDownload: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(
          `/api/v1/files/download/?path=${encodeURIComponent(entry.path)}`,
          { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const blob = await response.blob();
        if (cancelled) return;
        const obj = URL.createObjectURL(blob);
        revoked = obj;
        setUrl(obj);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Aperçu impossible.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [entry.path, token]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-cp-border bg-white shadow-2xl dark:border-ink-700 dark:bg-ink-950">
        <div className="flex items-center justify-between gap-2 border-b border-cp-border px-3 py-2 dark:border-ink-800">
          <p className="truncate text-sm font-semibold">{entry.name}</p>
          <div className="flex shrink-0 items-center gap-1">
            <button type="button" className="vz-btn-ghost vz-btn-sm" onClick={onDownload}>
              <Download className="h-3.5 w-3.5" />
              Télécharger
            </button>
            <button
              type="button"
              className="inline-flex h-8 w-8 items-center justify-center rounded hover:bg-cp-canvas dark:hover:bg-ink-900"
              onClick={onClose}
              aria-label="Fermer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="flex min-h-[240px] flex-1 items-center justify-center overflow-auto bg-[#111] p-4">
          {loading && <Loader2 className="h-6 w-6 animate-spin text-white/70" />}
          {error && <p className="text-sm text-red-300">{error}</p>}
          {url && !loading && (
            <img
              src={url}
              alt={entry.name}
              className="max-h-[70vh] max-w-full object-contain"
            />
          )}
        </div>
      </div>
    </div>
  );
}
