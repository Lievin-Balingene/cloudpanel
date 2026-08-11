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
    <div className="vz-panel p-3 sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold sm:text-xl">{title}</h1>
          {subtitle && <p className="mt-0.5 text-sm text-cp-muted">{subtitle}</p>}
        </div>
        {actions && <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">{actions}</div>}
      </div>
      {stats && stats.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-4 text-sm">
          {stats.map((s) => (
            <div key={s.label} className="min-w-[4.5rem]">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">
                {s.label}
              </p>
              <p className="text-lg font-semibold text-cp-text">{s.value}</p>
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
    <div className="px-4 py-10 text-center text-cp-muted">
      <div className="mx-auto mb-2 flex h-8 w-8 items-center justify-center opacity-40">{icon}</div>
      <p>{message}</p>
      {action && <div className="mt-3 flex justify-center">{action}</div>}
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
      <div className="flex gap-0.5 p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition ${
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
