import type { LucideIcon } from "lucide-react";
import { clsx } from "clsx";

interface MetricCardProps {
  title: string;
  value: string;
  hint?: string;
  icon: LucideIcon;
  loading?: boolean;
}

export function MetricCard({ title, value, hint, icon: Icon, loading }: MetricCardProps) {
  return (
    <article className="vz-panel p-5">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{title}</p>
        <span className="rounded-lg bg-accent/10 p-2 text-accent">
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p
        className={clsx(
          "font-display text-2xl font-semibold tracking-tight",
          loading && "animate-pulse-soft",
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-ink-500 dark:text-ink-400">{hint}</p> : null}
    </article>
  );
}
