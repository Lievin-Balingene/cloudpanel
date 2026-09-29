import { useMutation, useQuery } from "@tanstack/react-query";
import { Activity, Cpu, HardDrive, MemoryStick, RefreshCw, Zap } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageChrome";
import { useState } from "react";

interface PulseAccountRow {
  user?: string;
  active?: boolean;
  memory_current_bytes?: number;
  tasks_current?: number;
  disk_bytes?: number;
  inodes_used?: number;
  limits?: Record<string, number | string>;
}

interface PulseOverview {
  engine: string;
  brand: string;
  tagline: string;
  accounts_tracked: number;
  slices_active: number;
  provision_mode: string;
  accounts: PulseAccountRow[];
}

interface PulseStatus {
  brand: string;
  username: string;
  active: boolean;
  mock?: boolean;
  cpu: { millicores_limit: number | null; unlimited: boolean; usage_usec: number };
  memory: {
    used_mb: number;
    limit_mb: number | null;
    percent: number | null;
    unlimited: boolean;
  };
  tasks: { current: number; limit: number | null; percent: number | null };
  disk: { used_mb: number; percent: number | null };
  inodes: { used: number; limit: number | null; percent: number | null };
  slice: string;
}

function Bar({ pct, label }: { pct: number | null | undefined; label: string }) {
  const v = pct == null ? 0 : Math.min(100, Math.max(0, pct));
  const color =
    v >= 90 ? "bg-rose-500" : v >= 70 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div>
      <div className="mb-1 flex justify-between text-[11px] text-cp-muted">
        <span>{label}</span>
        <span>{pct == null ? "∞" : `${pct}%`}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-cp-canvas dark:bg-ink-900">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct == null ? 8 : v}%` }} />
      </div>
    </div>
  );
}

export function PulseManager({ title, mode = "whm" }: { title: string; mode?: "whm" | "client" }) {
  const [error, setError] = useState<string | null>(null);

  const overview = useQuery({
    queryKey: ["pulse-overview"],
    queryFn: () => apiRequest<PulseOverview>("/packages/pulse/"),
    enabled: mode === "whm",
    refetchInterval: 15_000,
  });

  const mine = useQuery({
    queryKey: ["pulse-mine"],
    queryFn: () => apiRequest<PulseStatus>("/packages/pulse/mine/"),
    enabled: mode === "client",
    refetchInterval: 10_000,
  });

  const refresh = useMutation({
    mutationFn: async () => {
      if (mode === "whm") await overview.refetch();
      else await mine.refetch();
    },
    onError: (e: Error) => setError(e.message),
  });

  const data = mode === "whm" ? overview.data : null;
  const status = mode === "client" ? mine.data : null;

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle={
          data?.tagline ||
          status?.brand ||
          "Resource Governor — cgroups v2 / systemd, sans noyau propriétaire"
        }
        stats={
          mode === "whm"
            ? [
                { label: "Comptes", value: data?.accounts_tracked ?? "—" },
                { label: "Slices actifs", value: data?.slices_active ?? "—" },
                { label: "Mode", value: data?.provision_mode ?? "—" },
              ]
            : [
                { label: "Slice", value: status?.active ? "actif" : "inactif" },
                {
                  label: "RAM",
                  value: status
                    ? `${status.memory.used_mb}${status.memory.limit_mb ? ` / ${status.memory.limit_mb}` : ""} Mo`
                    : "—",
                },
              ]
        }
        actions={
          <button
            type="button"
            className="vz-btn-ghost inline-flex items-center gap-1.5 text-sm"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
          >
            <RefreshCw className={`h-4 w-4 ${refresh.isPending ? "animate-spin" : ""}`} />
            Actualiser
          </button>
        }
      />

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
          {error}
        </p>
      )}

      <div className="vz-panel overflow-hidden p-4">
        <div className="flex items-start gap-3">
          <Zap className="mt-0.5 h-8 w-8 shrink-0 text-cp-orange" />
          <div className="text-sm leading-relaxed">
            <p className="font-semibold text-cp-navy dark:text-white">V-zone Pulse</p>
            <p className="mt-1 text-cp-muted">
              Limites CPU, RAM, processus et I/O par compte via <strong>cgroups v2</strong> et
              slices systemd. Les apps (Python, Node, cron) démarrent dans le slice via{" "}
              <code className="text-xs">vzone-runas</code>. PHP-FPM aligne{" "}
              <code className="text-xs">pm.max_children</code> et{" "}
              <code className="text-xs">memory_limit</code> sur le plan.
            </p>
          </div>
        </div>
      </div>

      {mode === "client" && status && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="vz-panel space-y-3 p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Cpu className="h-4 w-4 text-cp-orange" /> CPU
            </div>
            <p className="text-xs text-cp-muted">
              {status.cpu.unlimited
                ? "Illimité"
                : `${status.cpu.millicores_limit} millicores`}
            </p>
          </div>
          <div className="vz-panel space-y-3 p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <MemoryStick className="h-4 w-4 text-cp-orange" /> Mémoire
            </div>
            <Bar pct={status.memory.percent} label={`${status.memory.used_mb} Mo`} />
          </div>
          <div className="vz-panel space-y-3 p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Activity className="h-4 w-4 text-cp-orange" /> Processus
            </div>
            <Bar
              pct={status.tasks.percent}
              label={`${status.tasks.current}${status.tasks.limit ? ` / ${status.tasks.limit}` : ""}`}
            />
          </div>
          <div className="vz-panel space-y-3 p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <HardDrive className="h-4 w-4 text-cp-orange" /> Disque / inodes
            </div>
            <Bar pct={status.disk.percent} label={`${status.disk.used_mb} Mo`} />
            <Bar
              pct={status.inodes.percent}
              label={`${status.inodes.used}${status.inodes.limit ? ` / ${status.inodes.limit}` : ""} inodes`}
            />
          </div>
        </div>
      )}

      {mode === "whm" && (
        <div className="vz-panel overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
              <tr>
                <th className="px-3 py-2">Compte</th>
                <th className="px-3 py-2">Slice</th>
                <th className="px-3 py-2">RAM</th>
                <th className="px-3 py-2">Tasks</th>
                <th className="px-3 py-2">Disque</th>
                <th className="px-3 py-2">Inodes</th>
              </tr>
            </thead>
            <tbody>
              {(data?.accounts || []).length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-8 text-center text-cp-muted">
                    Aucun slice Pulse. Assignez un package à un compte pour activer les limites.
                  </td>
                </tr>
              ) : (
                (data?.accounts || []).map((row) => (
                  <tr
                    key={row.user}
                    className="border-t border-cp-border dark:border-ink-800"
                  >
                    <td className="px-3 py-2 font-medium">{row.user}</td>
                    <td className="px-3 py-2 text-xs">
                      {row.active ? (
                        <span className="text-emerald-600">actif</span>
                      ) : (
                        <span className="text-cp-muted">inactif</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {Math.round((row.memory_current_bytes || 0) / (1024 * 1024))} Mo
                    </td>
                    <td className="px-3 py-2 text-xs">{row.tasks_current ?? 0}</td>
                    <td className="px-3 py-2 text-xs">
                      {Math.round((row.disk_bytes || 0) / (1024 * 1024))} Mo
                    </td>
                    <td className="px-3 py-2 text-xs">{row.inodes_used ?? 0}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
