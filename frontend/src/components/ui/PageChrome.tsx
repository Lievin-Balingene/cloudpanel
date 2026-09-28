import type { ReactNode } from "react";

export function StatusDot({
  status,
  label,
}: {
  status: "active" | "suspended" | "inactive" | "error" | "ok" | string;
  label?: string;
}) {
  const color =
    status === "active" || status === "ok" || status === "running"
      ? "bg-cp-success"
      : status === "suspended" || status === "error" || status === "stopped"
        ? "bg-cp-danger"
        : "bg-cp-muted";
  const text =
    label ||
    (status === "active"
      ? "Actif"
      : status === "suspended"
        ? "Suspendu"
        : status === "running"
          ? "En cours"
          : status === "stopped"
            ? "Arrêté"
            : status);
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-cp-muted">
      <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
      {text}
    </span>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  stats,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  stats?: { label: string; value: string | number }[];
}) {
  return (
    <div className="vz-panel p-3.5 sm:p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold tracking-tight sm:text-xl">{title}</h1>
          {subtitle && <p className="mt-1 max-w-2xl text-sm leading-relaxed text-cp-muted">{subtitle}</p>}
        </div>
        {actions && (
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
            {actions}
          </div>
        )}
      </div>
      {stats && stats.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:flex sm:flex-wrap sm:gap-5">
          {stats.map((s) => (
            <div
              key={s.label}
              className="min-w-0 rounded-lg bg-cp-canvas/80 px-3 py-2 dark:bg-ink-900/60 sm:min-w-[4.5rem] sm:bg-transparent sm:p-0 dark:sm:bg-transparent"
            >
              <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">
                {s.label}
              </p>
              <p className="text-lg font-semibold tabular-nums text-cp-text">{s.value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function EmptyState({
  icon,
  message,
  action,
}: {
  icon: ReactNode;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="px-4 py-12 text-center text-cp-muted">
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-cp-canvas text-cp-orange opacity-90 dark:bg-ink-900">
        {icon}
      </div>
      <p className="mx-auto max-w-sm text-sm leading-relaxed">{message}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export type TabItem = {
  id: string;
  label: string;
  count?: number;
  icon?: ReactNode;
};

export function Tabs({
  tabs,
  active,
  onChange,
  trailing,
}: {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  trailing?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cp-border px-2 dark:border-ink-800">
      <div className="-mx-1 flex gap-0.5 overflow-x-auto overscroll-x-contain p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={`inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition sm:min-h-0 sm:py-1.5 ${
              active === t.id
                ? "bg-cp-link-soft text-cp-navy dark:bg-ink-800 dark:text-ink-50"
                : "text-cp-muted hover:bg-cp-canvas hover:text-cp-text dark:hover:bg-ink-900"
            }`}
          >
            {t.icon}
            {t.label}
            {typeof t.count === "number" && (
              <span className="rounded-full bg-cp-canvas px-1.5 text-[10px] tabular-nums text-cp-muted dark:bg-ink-900">
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>
      {trailing}
    </div>
  );
}
