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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        className={`w-full rounded-[10px] border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950 ${
          wide ? "max-w-2xl" : "max-w-md"
        }`}
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <p className="font-semibold text-cp-text">{title}</p>
            {subtitle && <p className="mt-0.5 text-xs text-cp-muted">{subtitle}</p>}
          </div>
          <button
            type="button"
            className="rounded-md p-1 text-cp-muted hover:bg-cp-canvas hover:text-cp-text"
            onClick={onClose}
            aria-label="Fermer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
