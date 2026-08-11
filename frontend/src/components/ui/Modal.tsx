import type { ReactNode } from "react";
import { X } from "lucide-react";

export function Modal({
  title,
  subtitle,
  onClose,
  children,
  wide,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Fermer"
        onClick={onClose}
      />
      <div
        className={`relative z-10 flex w-full max-h-[min(92dvh,720px)] flex-col overflow-hidden rounded-t-[14px] border border-cp-border bg-white shadow-xl dark:border-ink-700 dark:bg-ink-950 sm:rounded-[10px] ${
          wide ? "max-w-2xl" : "max-w-md"
        }`}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-cp-border/80 px-4 py-3 dark:border-ink-800">
          <div className="min-w-0">
            <p className="font-semibold text-cp-text">{title}</p>
            {subtitle && <p className="mt-0.5 text-xs text-cp-muted">{subtitle}</p>}
          </div>
          <button
            type="button"
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-cp-muted hover:bg-cp-canvas hover:text-cp-text"
            onClick={onClose}
            aria-label="Fermer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
          {children}
        </div>
      </div>
    </div>
  );
}
