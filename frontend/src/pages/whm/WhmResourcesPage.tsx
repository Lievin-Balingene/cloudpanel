import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, HardDrive, MemoryStick, RefreshCw } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiRequest } from "@/lib/api";
import { EmptyState, PageHeader } from "@/components/ui/PageChrome";
import type { HistoryPoint } from "@/types";

function latest(history: HistoryPoint[]) {
  return history.length ? history[history.length - 1] : null;
}

function MetricPill({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-cp-border/70 bg-white px-3.5 py-3 dark:border-ink-700 dark:bg-ink-950">
      <span
        className="flex h-9 w-9 items-center justify-center rounded-lg"
        style={{ backgroundColor: `${color}18`, color }}
      >
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">{label}</p>
        <p className="text-lg font-semibold tabular-nums text-cp-text">{value}</p>
      </div>
    </div>
  );
}

export function WhmResourcesPage() {
  const qc = useQueryClient();
  const { data: history = [], isLoading } = useQuery({
    queryKey: ["dashboard-history"],
    queryFn: () => apiRequest<HistoryPoint[]>("/dashboard/history/?hours=24"),
    refetchInterval: 15000,
  });

  const capture = useMutation({
    mutationFn: () => apiRequest("/dashboard/capture/", { method: "POST", body: "{}" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard-history"] });
      void qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
  });

  const chartData = history.map((h) => ({
    ...h,
    time: new Date(h.collected_at).toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
    }),
  }));

  const last = latest(history);

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title="Ressources serveur"
        subtitle="Historique CPU, mémoire et disque sur 24 h. Les captures automatiques complètent les points manuels."
        stats={[
          { label: "Points", value: history.length || "—" },
          {
            label: "Dernière mesure",
            value: last
              ? new Date(last.collected_at).toLocaleTimeString("fr-FR", {
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : "—",
          },
        ]}
        actions={
          <button
            className="vz-btn-primary"
            type="button"
            onClick={() => capture.mutate()}
            disabled={capture.isPending}
          >
            <RefreshCw className={`h-4 w-4 ${capture.isPending ? "animate-spin" : ""}`} />
            {capture.isPending ? "Capture…" : "Capturer maintenant"}
          </button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricPill
          icon={Activity}
          label="CPU"
          value={last ? `${last.cpu_percent.toFixed(0)}%` : "—"}
          color="#1a5fb4"
        />
        <MetricPill
          icon={MemoryStick}
          label="Mémoire"
          value={last ? `${last.ram_percent.toFixed(0)}%` : "—"}
          color="#c45c26"
        />
        <MetricPill
          icon={HardDrive}
          label="Disque"
          value={last ? `${last.disk_percent.toFixed(0)}%` : "—"}
          color="#2e7d32"
        />
      </div>

      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border px-4 py-2.5 text-sm font-semibold dark:border-ink-800">
          Historique 24 h
        </div>
        <div className="h-80 p-3 sm:p-4">
          {isLoading && (
            <p className="flex h-full items-center justify-center text-sm text-cp-muted">
              Chargement…
            </p>
          )}
          {!isLoading && chartData.length === 0 && (
            <EmptyState
              icon={<Activity className="h-5 w-5" />}
              message="Aucun historique. Lancez une capture pour démarrer le suivi."
              action={
                <button
                  type="button"
                  className="vz-btn-primary"
                  onClick={() => capture.mutate()}
                  disabled={capture.isPending}
                >
                  Capturer maintenant
                </button>
              }
            />
          )}
          {chartData.length > 0 && (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="cpuFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1a5fb4" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#1a5fb4" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="ramFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#c45c26" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="#c45c26" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="diskFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2e7d32" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="#2e7d32" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#d5dde5" vertical={false} />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={36}
                  unit="%"
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 10,
                    border: "1px solid #d5dde5",
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area
                  type="monotone"
                  dataKey="cpu_percent"
                  name="CPU"
                  stroke="#1a5fb4"
                  fill="url(#cpuFill)"
                  strokeWidth={2}
                  dot={false}
                />
                <Area
                  type="monotone"
                  dataKey="ram_percent"
                  name="Mémoire"
                  stroke="#c45c26"
                  fill="url(#ramFill)"
                  strokeWidth={2}
                  dot={false}
                />
                <Area
                  type="monotone"
                  dataKey="disk_percent"
                  name="Disque"
                  stroke="#2e7d32"
                  fill="url(#diskFill)"
                  strokeWidth={2}
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
