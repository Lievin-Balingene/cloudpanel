import { CheckCircle2, Loader2, X, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useOperationsStore } from "@/stores/operations";

function ProgressTrack({
  percent,
  status,
}: {
  percent: number;
  status: "running" | "success" | "error";
}) {
  const indeterminate = status === "running" && percent < 0;
  const width = status === "success" || status === "error" ? 100 : Math.max(0, Math.min(100, percent));

  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-cp-canvas dark:bg-ink-800">
      {indeterminate ? (
        <div className="vz-progress-indeterminate h-full w-1/3 rounded-full bg-cp-link" />
      ) : (
        <div
          className={`h-full rounded-full transition-[width] duration-300 ease-out ${
            status === "error"
              ? "bg-cp-danger"
              : status === "success"
                ? "bg-cp-success"
                : "bg-cp-link"
          }`}
          style={{ width: `${width}%` }}
        />
      )}
    </div>
  );
}

export function OperationProgressHost() {
  const items = useOperationsStore((s) => s.items);
  const dismiss = useOperationsStore((s) => s.dismiss);
  const clearFinished = useOperationsStore((s) => s.clearFinished);
  const [pulse, setPulse] = useState(0);

  // Relance le rendu pour l'animation indéterminée
  useEffect(() => {
    if (!items.some((i) => i.status === "running" && i.percent < 0)) return;
    const t = window.setInterval(() => setPulse((n) => n + 1), 400);
    return () => window.clearInterval(t);
  }, [items]);

  if (!items.length) return null;

  void pulse;

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-[70] flex w-full max-w-sm flex-col gap-2 p-0 sm:bottom-5 sm:right-5"
      aria-live="polite"
    >
      <div className="pointer-events-auto overflow-hidden rounded-xl border border-cp-border bg-white/95 shadow-lg backdrop-blur dark:border-ink-700 dark:bg-ink-950/95">
        <div className="flex items-center justify-between border-b border-cp-border px-3 py-2 dark:border-ink-800">
          <p className="text-xs font-semibold uppercase tracking-wide text-cp-muted">
            Opérations
          </p>
          {items.some((i) => i.status !== "running") && (
            <button
              type="button"
              className="text-[11px] text-cp-link hover:underline"
              onClick={() => clearFinished()}
            >
              Effacer
            </button>
          )}
        </div>
        <ul className="max-h-72 space-y-0 divide-y divide-cp-border overflow-y-auto dark:divide-ink-800">
          {items.map((op) => (
            <li key={op.id} className="px-3 py-2.5">
              <div className="mb-1.5 flex items-start gap-2">
                <span className="mt-0.5 shrink-0">
                  {op.status === "running" && (
                    <Loader2 className="h-4 w-4 animate-spin text-cp-link" />
                  )}
                  {op.status === "success" && (
                    <CheckCircle2 className="h-4 w-4 text-cp-success" />
                  )}
                  {op.status === "error" && <XCircle className="h-4 w-4 text-cp-danger" />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-cp-text">{op.title}</p>
                  <p
                    className={`truncate text-xs ${
                      op.status === "error" ? "text-cp-danger" : "text-cp-muted"
                    }`}
                  >
                    {op.error || op.detail || (op.status === "running" ? "En cours…" : "")}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {op.status === "running" && op.percent >= 0 && (
                    <span className="text-[10px] tabular-nums text-cp-muted">
                      {Math.round(op.percent)}%
                    </span>
                  )}
                  {op.status !== "running" && (
                    <button
                      type="button"
                      className="rounded p-0.5 text-cp-muted hover:bg-cp-canvas hover:text-cp-text"
                      aria-label="Fermer"
                      onClick={() => dismiss(op.id)}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
              <ProgressTrack percent={op.percent} status={op.status} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
