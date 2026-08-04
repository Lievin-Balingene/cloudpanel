import type { ReactNode } from "react";

export function IconAction({
  label,
  onClick,
  disabled,
  danger,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent transition
        hover:border-cp-border hover:bg-cp-canvas disabled:cursor-not-allowed disabled:opacity-40
        dark:hover:border-ink-600 dark:hover:bg-ink-900
        ${
          danger
            ? "text-cp-danger hover:bg-red-50 dark:hover:bg-red-950/40"
            : "text-cp-muted hover:text-cp-navy dark:hover:text-ink-100"
        }`}
    >
      {children}
    </button>
  );
}
