import type { ReactNode } from "react";

const TONE = {
  default:
    "text-cp-muted hover:border-cp-border hover:bg-cp-canvas hover:text-cp-navy dark:hover:border-ink-600 dark:hover:bg-ink-900 dark:hover:text-ink-100",
  success:
    "text-emerald-600 hover:border-emerald-200 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:border-emerald-800 dark:hover:bg-emerald-950/40",
  danger:
    "text-cp-danger hover:border-red-200 hover:bg-red-50 dark:hover:border-red-900 dark:hover:bg-red-950/40",
  warning:
    "text-amber-600 hover:border-amber-200 hover:bg-amber-50 dark:text-amber-400 dark:hover:border-amber-800 dark:hover:bg-amber-950/40",
  info: "text-sky-600 hover:border-sky-200 hover:bg-sky-50 dark:text-sky-400 dark:hover:border-sky-800 dark:hover:bg-sky-950/40",
  accent:
    "text-cp-orange hover:border-orange-200 hover:bg-orange-50 dark:hover:border-orange-900 dark:hover:bg-orange-950/30",
} as const;

export function IconAction({
  label,
  onClick,
  disabled,
  danger,
  tone,
  size = "md",
  active,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  tone?: keyof typeof TONE;
  size?: "sm" | "md";
  active?: boolean;
  children: ReactNode;
}) {
  const resolved = tone ?? (danger ? "danger" : "default");
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex items-center justify-center rounded-md border border-transparent transition
        disabled:cursor-not-allowed disabled:opacity-40
        ${size === "sm" ? "h-9 w-9 sm:h-7 sm:w-7" : "h-9 w-9 sm:h-8 sm:w-8"}
        ${TONE[resolved]}
        ${active ? "border-cp-link/40 bg-cp-link-soft text-cp-link" : ""}`}
    >
      {children}
    </button>
  );
}
