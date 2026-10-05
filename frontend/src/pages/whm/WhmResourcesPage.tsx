import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Bell,
  Cpu,
  Gauge,
  HardDrive,
  MemoryStick,
  Network,
  Play,
  RefreshCw,
  RotateCcw,
  Server,
  Square,
  Thermometer,
  Users,
  Wifi,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { EmptyState, PageHeader, StatusDot, Tabs } from "@/components/ui/PageChrome";
import type { HistoryPoint } from "@/types";

type ServiceAction = "start" | "stop" | "restart";

interface ServiceInfo {
  name: string;
  active: boolean;
  source?: string;
  unit?: string | null;
  manageable?: boolean;
}

interface ServerStatus {
  health: "healthy" | "degraded" | "critical" | string;
  collected_at: string;
  identity: {
    hostname: string;
    operating_system: string;
    product: string;
    version: string;
    platform?: string;
    uptime_seconds: number;
    boot_time: number;
    process_count: number;
    cpu_count_logical: number;
    cpu_count_physical: number;
  };
  cpu: {
    percent: number;
    per_cpu: number[];
    freq: { current: number; min: number | null; max: number | null } | null;
    load: { "1": number | null; "5": number | null; "15": number | null };
  };
  memory: {
    total: number;
    available: number;
    used: number;
    free: number;
    percent: number;
    cached: number;
    buffers: number;
    shared: number;
  };
  swap: { total: number; used: number; free: number; percent: number };
  disks: {
    device: string;
    mountpoint: string;
    fstype: string;
    total: number;
    used: number;
    free: number;
    percent: number;
  }[];
  disk_io: {
    read_bytes: number;
    write_bytes: number;
    read_count: number;
    write_count: number;
  } | null;
  network: {
    bytes_sent: number;
    bytes_recv: number;
    rates: { sent_bps: number; recv_bps: number };
    interfaces: {
      name: string;
      ip: string;
      is_up: boolean;
      speed_mbps: number;
      bytes_sent: number;
      bytes_recv: number;
      packets_sent: number;
      packets_recv: number;
      errin: number;
      errout: number;
      dropin: number;
      dropout: number;
    }[];
    connections: {
      total: number;
      established: number;
      listen: number;
      time_wait: number;
      close_wait: number;
      other: number;
    };
  };
  processes: {
    top_cpu: ProcessRow[];
    top_memory: ProcessRow[];
  };
  services: ServiceInfo[];
  services_down: string[];
  temperatures: { chip: string; label: string; current: number; high: number | null; critical: number | null }[];
  fans: { chip: string; label: string; rpm: number }[];
  users: { name: string; terminal: string; host: string; started: number | null }[];
  alerts: { open: number; critical: number; warning: number };
}

interface ProcessRow {
  pid: number;
  name: string;
  user: string;
  cpu_percent: number;
  memory_percent: number;
  status: string;
}

function formatBytes(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs < 1024) return `${n.toFixed(0)} o`;
  const units = ["Ko", "Mo", "Go", "To", "Po"];
  let v = abs / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  const sign = n < 0 ? "-" : "";
  return `${sign}${v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2)} ${units[i]}`;
}

function formatBps(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n) || n <= 0) return "0 o/s";
  return `${formatBytes(n)}/s`;
}

function formatUptime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}j ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function tone(percent: number | undefined | null): "ok" | "warn" | "bad" | "idle" {
  if (percent == null || Number.isNaN(percent)) return "idle";
  if (percent >= 90) return "bad";
  if (percent >= 75) return "warn";
  return "ok";
}

const toneColor = {
  ok: "#2e7d32",
  warn: "#c45c26",
  bad: "#c62828",
  idle: "#94a3b8",
};

const healthMeta: Record<string, { label: string; className: string }> = {
  healthy: {
    label: "Sain",
    className:
      "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900",
  },
  degraded: {
    label: "Dégradé",
    className:
      "bg-amber-50 text-amber-900 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-900",
  },
  critical: {
    label: "Critique",
    className:
      "bg-rose-50 text-rose-800 ring-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-900",
  },
};

function GaugeCard({
  icon: Icon,
  label,
  percent,
  value,
  detail,
  accent,
}: {
  icon: typeof Cpu;
  label: string;
  percent: number;
  value: string;
  detail?: string;
  accent?: string;
}) {
  const t = tone(percent);
  const color = accent || toneColor[t];
  const pct = Math.min(100, Math.max(0, percent));
  const r = 36;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-cp-border/70 bg-white p-4 dark:border-ink-700 dark:bg-ink-950">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-1"
        style={{ background: `linear-gradient(90deg, ${color}, transparent)` }}
      />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-cp-muted">
            <Icon className="h-3.5 w-3.5" style={{ color }} />
            {label}
          </div>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight text-cp-text">{value}</p>
          {detail ? <p className="mt-1 text-xs text-cp-muted">{detail}</p> : null}
        </div>
        <svg width="88" height="88" viewBox="0 0 88 88" className="shrink-0">
          <circle cx="44" cy="44" r={r} fill="none" stroke="currentColor" strokeWidth="7" className="text-cp-canvas dark:text-ink-800" />
          <circle
            cx="44"
            cy="44"
            r={r}
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
            transform="rotate(-90 44 44)"
            className="transition-all duration-700 ease-out"
          />
          <text x="44" y="48" textAnchor="middle" className="fill-cp-text text-[13px] font-semibold" style={{ fontSize: 13 }}>
            {pct.toFixed(0)}%
          </text>
        </svg>
      </div>
    </div>
  );
}

function SectionCard({
  title,
  icon: Icon,
  action,
  children,
}: {
  title: string;
  icon: typeof Server;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="vz-panel overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-cp-border px-4 py-2.5 dark:border-ink-800">
        <div className="flex items-center gap-2 text-sm font-semibold text-cp-text">
          <Icon className="h-4 w-4 text-cp-muted" />
          {title}
        </div>
        {action}
      </div>
      <div className="p-3.5 sm:p-4">{children}</div>
    </div>
  );
}

function ProgressRow({
  label,
  sub,
  percent,
  right,
}: {
  label: string;
  sub?: string;
  percent: number;
  right?: string;
}) {
  const t = tone(percent);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2 text-sm">
        <div className="min-w-0">
          <p className="truncate font-medium text-cp-text">{label}</p>
          {sub ? <p className="truncate text-[11px] text-cp-muted">{sub}</p> : null}
        </div>
        <span className="shrink-0 tabular-nums text-cp-muted">{right ?? `${percent.toFixed(0)}%`}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-cp-canvas dark:bg-ink-800">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.min(100, Math.max(0, percent))}%`,
            backgroundColor: toneColor[t],
          }}
        />
      </div>
    </div>
  );
}

function ServiceActions({
  service,
  busy,
  onAction,
}: {
  service: ServiceInfo;
  busy: boolean;
  onAction: (name: string, action: ServiceAction) => void;
}) {
  const can = service.manageable !== false;
  return (
    <div className="flex shrink-0 items-center gap-0.5">
      <IconAction
        label={`Démarrer ${service.name}`}
        size="sm"
        tone="success"
        disabled={busy || !can}
        onClick={() => onAction(service.name, "start")}
      >
        <Play className="h-3.5 w-3.5" />
      </IconAction>
      <IconAction
        label={`Arrêter ${service.name}`}
        size="sm"
        tone="danger"
        disabled={busy || !can}
        onClick={() => onAction(service.name, "stop")}
      >
        <Square className="h-3.5 w-3.5" />
      </IconAction>
      <IconAction
        label={`Redémarrer ${service.name}`}
        size="sm"
        tone="accent"
        disabled={busy || !can}
        onClick={() => onAction(service.name, "restart")}
      >
        <RotateCcw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} />
      </IconAction>
    </div>
  );
}

export function WhmResourcesPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState("overview");
  const [hours, setHours] = useState(24);
  const [refreshMs, setRefreshMs] = useState(10000);
  const [procSort, setProcSort] = useState<"cpu" | "mem">("cpu");
  const [busyService, setBusyService] = useState<string | null>(null);
  const [svcError, setSvcError] = useState<string | null>(null);

  const { data: server, isLoading, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ["dashboard-server"],
    queryFn: () => apiRequest<ServerStatus>("/dashboard/server/"),
    refetchInterval: refreshMs,
  });

  const { data: historyData = [], isLoading: histLoading } = useQuery({
    queryKey: ["dashboard-history", hours],
    queryFn: () => apiRequest<HistoryPoint[]>(`/dashboard/history/?hours=${hours}`),
    refetchInterval: Math.max(refreshMs, 15000),
  });

  const capture = useMutation({
    mutationFn: () => apiRequest("/dashboard/capture/", { method: "POST", body: "{}" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard-history"] });
      void qc.invalidateQueries({ queryKey: ["dashboard-server"] });
      void qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
  });

  const serviceControl = useMutation({
    mutationFn: ({ name, action }: { name: string; action: ServiceAction }) =>
      apiRequest("/dashboard/services/control/", {
        method: "POST",
        body: JSON.stringify({ name, action }),
      }),
    onMutate: ({ name }) => {
      setBusyService(name);
      setSvcError(null);
    },
    onSuccess: () => {
      setSvcError(null);
      void qc.invalidateQueries({ queryKey: ["dashboard-server"] });
      void qc.invalidateQueries({ queryKey: ["monitoring-overview"] });
    },
    onError: (err: Error) => setSvcError(err.message),
    onSettled: () => setBusyService(null),
  });

  function onServiceAction(name: string, action: ServiceAction) {
    if (action === "stop" && (name === "sshd" || name === "vzone-api")) {
      const ok = window.confirm(
        name === "sshd"
          ? "Arrêter SSH peut vous couper l’accès distant. Continuer ?"
          : "Arrêter vzone-api va couper le panneau jusqu’à un redémarrage manuel. Continuer ?",
      );
      if (!ok) return;
    }
    serviceControl.mutate({ name, action });
  }

  const chartData = useMemo(
    () =>
      historyData.map((h) => ({
        ...h,
        time: new Date(h.collected_at).toLocaleTimeString("fr-FR", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      })),
    [historyData],
  );

  const netChart = useMemo(() => {
    return historyData.map((h, i) => {
      const prev = i > 0 ? historyData[i - 1] : null;
      let sent = 0;
      let recv = 0;
      if (prev) {
        const dt = (new Date(h.collected_at).getTime() - new Date(prev.collected_at).getTime()) / 1000;
        if (dt > 0) {
          sent = Math.max(0, (h.net_bytes_sent - prev.net_bytes_sent) / dt);
          recv = Math.max(0, (h.net_bytes_recv - prev.net_bytes_recv) / dt);
        }
      }
      return {
        time: new Date(h.collected_at).toLocaleTimeString("fr-FR", {
          hour: "2-digit",
          minute: "2-digit",
        }),
        sent_kbps: sent / 1024,
        recv_kbps: recv / 1024,
      };
    });
  }, [historyData]);

  const health = healthMeta[server?.health || ""] || {
    label: server?.health || "—",
    className: "bg-slate-50 text-slate-700 ring-slate-200 dark:bg-ink-900 dark:text-slate-300 dark:ring-ink-700",
  };

  const rootDisk = server?.disks.find((d) => d.mountpoint === "/") || server?.disks[0];
  const load1 = server?.cpu.load["1"];
  const cores = server?.identity.cpu_count_logical || 1;
  const loadPct = typeof load1 === "number" ? Math.min(100, (load1 / cores) * 100) : 0;

  const processes = procSort === "cpu" ? server?.processes.top_cpu : server?.processes.top_memory;

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title="Monitoring serveur"
        subtitle="Vue live complète : CPU, mémoire, disques, réseau, processus, services et historique."
        stats={[
          { label: "Hostname", value: server?.identity.hostname || "—" },
          { label: "Uptime", value: server ? formatUptime(server.identity.uptime_seconds) : "—" },
          { label: "Processus", value: server?.identity.process_count ?? "—" },
          {
            label: "Alertes",
            value: server ? server.alerts.open : "—",
          },
        ]}
        actions={
          <>
            <select
              className="vz-btn-ghost h-9 rounded-lg px-2 text-sm"
              value={refreshMs}
              onChange={(e) => setRefreshMs(Number(e.target.value))}
              title="Intervalle de rafraîchissement"
            >
              <option value={5000}>Live 5 s</option>
              <option value={10000}>Live 10 s</option>
              <option value={30000}>Live 30 s</option>
              <option value={60000}>Live 1 min</option>
            </select>
            <Link to="/whm/monitoring" className="vz-btn-ghost">
              <Bell className="h-4 w-4" />
              Alertes
              {server && server.alerts.open > 0 ? (
                <span className="rounded-md bg-rose-100 px-1.5 py-0.5 text-[10px] font-bold text-rose-700 dark:bg-rose-950 dark:text-rose-300">
                  {server.alerts.open}
                </span>
              ) : null}
            </Link>
            <button
              className="vz-btn-primary"
              type="button"
              onClick={() => capture.mutate()}
              disabled={capture.isPending}
            >
              <RefreshCw className={`h-4 w-4 ${capture.isPending || isFetching ? "animate-spin" : ""}`} />
              {capture.isPending ? "Capture…" : "Capturer"}
            </button>
          </>
        }
      />

      {/* Bannière santé */}
      <div className="flex flex-col gap-3 rounded-2xl border border-cp-border/70 bg-gradient-to-br from-white via-white to-cp-canvas/80 p-4 dark:border-ink-700 dark:from-ink-950 dark:via-ink-950 dark:to-ink-900 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-cp-navy/10 text-cp-navy dark:bg-sky-950/50 dark:text-sky-300">
            <Gauge className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${health.className}`}>
                {health.label}
              </span>
              <span className="text-sm font-semibold text-cp-text truncate">
                {server?.identity.product || "V-zone Admin"}
              </span>
            </div>
            <p className="mt-1 text-sm text-cp-muted">
              {server?.identity.operating_system || "—"}
              {server?.identity.platform ? ` · ${server.identity.platform}` : ""}
              {server?.identity.cpu_count_logical
                ? ` · ${server.identity.cpu_count_physical || "?"}p / ${server.identity.cpu_count_logical}c`
                : ""}
            </p>
            <p className="mt-0.5 text-[11px] text-cp-muted">
              Dernière mesure{" "}
              {dataUpdatedAt
                ? new Date(dataUpdatedAt).toLocaleTimeString("fr-FR", {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })
                : "—"}
              {isLoading ? " · chargement…" : isFetching ? " · actualisation…" : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {server && server.services_down.length > 0 ? (
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-rose-50 px-2.5 py-1.5 text-xs font-medium text-rose-800 ring-1 ring-inset ring-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-900">
              <AlertTriangle className="h-3.5 w-3.5" />
              {server.services_down.length} service{server.services_down.length > 1 ? "s" : ""} down
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-50 px-2.5 py-1.5 text-xs font-medium text-emerald-800 ring-1 ring-inset ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900">
              Services OK
            </span>
          )}
          {server && server.network.rates ? (
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-cp-border/70 bg-white px-2.5 py-1.5 text-xs text-cp-muted dark:border-ink-700 dark:bg-ink-900">
              <Wifi className="h-3.5 w-3.5" />
              ↓ {formatBps(server.network.rates.recv_bps)} · ↑ {formatBps(server.network.rates.sent_bps)}
            </span>
          ) : null}
        </div>
      </div>

      {/* Gauges */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <GaugeCard
          icon={Cpu}
          label="CPU"
          percent={server?.cpu.percent ?? 0}
          value={server ? `${server.cpu.percent.toFixed(0)}%` : "—"}
          detail={
            server?.cpu.freq
              ? `${server.cpu.freq.current.toFixed(0)} MHz · load ${load1?.toFixed(2) ?? "—"}`
              : `load ${load1?.toFixed(2) ?? "—"}`
          }
        />
        <GaugeCard
          icon={MemoryStick}
          label="Mémoire"
          percent={server?.memory.percent ?? 0}
          value={server ? `${server.memory.percent.toFixed(0)}%` : "—"}
          detail={
            server
              ? `${formatBytes(server.memory.used)} / ${formatBytes(server.memory.total)}`
              : undefined
          }
        />
        <GaugeCard
          icon={HardDrive}
          label="Disque /"
          percent={rootDisk?.percent ?? 0}
          value={rootDisk ? `${rootDisk.percent.toFixed(0)}%` : "—"}
          detail={
            rootDisk ? `${formatBytes(rootDisk.used)} / ${formatBytes(rootDisk.total)}` : undefined
          }
        />
        <GaugeCard
          icon={Activity}
          label="Charge"
          percent={loadPct}
          value={typeof load1 === "number" ? load1.toFixed(2) : "—"}
          detail={
            server
              ? `1/5/15 · ${server.cpu.load["1"]?.toFixed(2) ?? "—"} / ${server.cpu.load["5"]?.toFixed(2) ?? "—"} / ${server.cpu.load["15"]?.toFixed(2) ?? "—"}`
              : undefined
          }
          accent="#1a5fb4"
        />
      </div>

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "overview", label: "Vue d'ensemble" },
          { id: "history", label: "Historique" },
          { id: "cpu", label: "CPU & RAM" },
          { id: "disks", label: "Disques" },
          { id: "network", label: "Réseau" },
          { id: "processes", label: "Processus" },
          { id: "services", label: "Services" },
        ]}
      />

      {tab === "overview" && (
        <div className="grid gap-4 xl:grid-cols-2">
          <SectionCard title="Services critiques" icon={Server}>
            {svcError ? (
              <p className="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
                {svcError}
              </p>
            ) : null}
            {isLoading && !server ? (
              <p className="text-sm text-cp-muted">Chargement…</p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {(server?.services || []).map((s) => (
                  <div
                    key={s.name}
                    className="flex items-center justify-between gap-2 rounded-xl border border-cp-border/60 bg-cp-canvas/40 px-3 py-2.5 dark:border-ink-700 dark:bg-ink-900/40"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-cp-text">{s.name}</p>
                      <StatusDot status={s.active ? "ok" : "error"} label={s.active ? "UP" : "DOWN"} />
                    </div>
                    <ServiceActions
                      service={s}
                      busy={busyService === s.name}
                      onAction={onServiceAction}
                    />
                  </div>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard title="Connexions & sessions" icon={Network}>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {[
                ["Total", server?.network.connections.total],
                ["Established", server?.network.connections.established],
                ["Listen", server?.network.connections.listen],
                ["Time-wait", server?.network.connections.time_wait],
                ["Close-wait", server?.network.connections.close_wait],
                ["Autres", server?.network.connections.other],
              ].map(([label, value]) => (
                <div
                  key={String(label)}
                  className="rounded-xl border border-cp-border/60 bg-cp-canvas/40 px-3 py-2.5 dark:border-ink-700 dark:bg-ink-900/40"
                >
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">
                    {label}
                  </p>
                  <p className="mt-0.5 text-lg font-semibold tabular-nums text-cp-text">
                    {value ?? "—"}
                  </p>
                </div>
              ))}
            </div>
            {server && server.users.length > 0 ? (
              <div className="mt-4 border-t border-cp-border/60 pt-3 dark:border-ink-800">
                <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-cp-muted">
                  <Users className="h-3.5 w-3.5" />
                  Sessions connectées
                </div>
                <div className="space-y-1.5">
                  {server.users.slice(0, 8).map((u, i) => (
                    <div key={`${u.name}-${u.terminal}-${i}`} className="flex justify-between gap-2 text-sm">
                      <span className="font-medium text-cp-text">{u.name}</span>
                      <span className="truncate text-cp-muted">
                        {u.terminal} · {u.host}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Volumes disque" icon={HardDrive}>
            <div className="space-y-3">
              {(server?.disks || []).slice(0, 6).map((d) => (
                <ProgressRow
                  key={`${d.device}-${d.mountpoint}`}
                  label={d.mountpoint}
                  sub={`${d.device} · ${d.fstype}`}
                  percent={d.percent}
                  right={`${formatBytes(d.used)} / ${formatBytes(d.total)}`}
                />
              ))}
              {!server?.disks?.length && !isLoading ? (
                <EmptyState icon={<HardDrive className="h-5 w-5" />} message="Aucun volume détecté." />
              ) : null}
            </div>
          </SectionCard>

          <SectionCard
            title="Températures"
            icon={Thermometer}
            action={
              server?.fans?.length ? (
                <span className="text-xs text-cp-muted">{server.fans.length} ventilateur(s)</span>
              ) : null
            }
          >
            {server?.temperatures?.length ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {server.temperatures.slice(0, 8).map((t, i) => (
                  <div
                    key={`${t.chip}-${t.label}-${i}`}
                    className="rounded-xl border border-cp-border/60 bg-cp-canvas/40 px-3 py-2.5 dark:border-ink-700 dark:bg-ink-900/40"
                  >
                    <p className="truncate text-xs text-cp-muted">{t.label}</p>
                    <p className="text-lg font-semibold tabular-nums text-cp-text">
                      {t.current.toFixed(0)}°C
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-cp-muted">
                Capteurs non exposés sur cette machine (normal en VM / cloud).
              </p>
            )}
          </SectionCard>
        </div>
      )}

      {tab === "history" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {[6, 12, 24, 48, 72, 168].map((h) => (
              <button
                key={h}
                type="button"
                className={hours === h ? "vz-btn-primary vz-btn-sm" : "vz-btn-ghost vz-btn-sm"}
                onClick={() => setHours(h)}
              >
                {h < 24 ? `${h} h` : h === 24 ? "24 h" : `${h / 24} j`}
              </button>
            ))}
          </div>
          <SectionCard title={`Ressources · ${hours < 24 ? `${hours} h` : hours === 24 ? "24 h" : `${hours / 24} j`}`} icon={Activity}>
            <div className="h-80">
              {histLoading && (
                <p className="flex h-full items-center justify-center text-sm text-cp-muted">Chargement…</p>
              )}
              {!histLoading && chartData.length === 0 && (
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
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={36} unit="%" />
                    <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #d5dde5", fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area type="monotone" dataKey="cpu_percent" name="CPU" stroke="#1a5fb4" fill="url(#cpuFill)" strokeWidth={2} dot={false} />
                    <Area type="monotone" dataKey="ram_percent" name="Mémoire" stroke="#c45c26" fill="url(#ramFill)" strokeWidth={2} dot={false} />
                    <Area type="monotone" dataKey="disk_percent" name="Disque" stroke="#2e7d32" fill="url(#diskFill)" strokeWidth={2} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </SectionCard>

          <SectionCard title="Débit réseau (estimé)" icon={Wifi}>
            <div className="h-64">
              {netChart.length > 1 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={netChart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#d5dde5" vertical={false} />
                    <XAxis dataKey="time" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={48} unit=" Ko/s" />
                    <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #d5dde5", fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area type="monotone" dataKey="recv_kbps" name="Entrant" stroke="#1a5fb4" fill="#1a5fb422" strokeWidth={2} dot={false} />
                    <Area type="monotone" dataKey="sent_kbps" name="Sortant" stroke="#c45c26" fill="#c45c2622" strokeWidth={2} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <EmptyState icon={<Wifi className="h-5 w-5" />} message="Besoin d’au moins 2 points d’historique pour le débit." />
              )}
            </div>
          </SectionCard>
        </div>
      )}

      {tab === "cpu" && (
        <div className="grid gap-4 xl:grid-cols-2">
          <SectionCard title="Cœurs CPU" icon={Cpu}>
            {server?.cpu.per_cpu?.length ? (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={server.cpu.per_cpu.map((p, i) => ({ core: `C${i}`, percent: p }))}
                    margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#d5dde5" vertical={false} />
                    <XAxis dataKey="core" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={32} />
                    <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #d5dde5", fontSize: 12 }} />
                    <Bar dataKey="percent" name="%" fill="#1a5fb4" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-sm text-cp-muted">Données par cœur indisponibles.</p>
            )}
          </SectionCard>

          <SectionCard title="Mémoire détaillée" icon={MemoryStick}>
            <div className="space-y-4">
              <ProgressRow
                label="RAM utilisée"
                sub={`Dispo ${formatBytes(server?.memory.available ?? 0)}`}
                percent={server?.memory.percent ?? 0}
                right={`${formatBytes(server?.memory.used ?? 0)} / ${formatBytes(server?.memory.total ?? 0)}`}
              />
              <ProgressRow
                label="Swap"
                percent={server?.swap.percent ?? 0}
                right={
                  server?.swap.total
                    ? `${formatBytes(server.swap.used)} / ${formatBytes(server.swap.total)}`
                    : "Aucun"
                }
              />
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {[
                  ["Cache", server?.memory.cached],
                  ["Buffers", server?.memory.buffers],
                  ["Shared", server?.memory.shared],
                  ["Libre", server?.memory.free],
                  ["Disponible", server?.memory.available],
                  ["Total", server?.memory.total],
                ].map(([label, value]) => (
                  <div
                    key={String(label)}
                    className="rounded-xl border border-cp-border/60 bg-cp-canvas/40 px-3 py-2 dark:border-ink-700 dark:bg-ink-900/40"
                  >
                    <p className="text-[11px] text-cp-muted">{label}</p>
                    <p className="text-sm font-semibold tabular-nums text-cp-text">
                      {formatBytes(Number(value) || 0)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </SectionCard>
        </div>
      )}

      {tab === "disks" && (
        <div className="space-y-4">
          <SectionCard title="Tous les volumes" icon={HardDrive}>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
                  <tr>
                    <th className="px-3 py-2">Montage</th>
                    <th className="px-3 py-2">Périphérique</th>
                    <th className="px-3 py-2">FS</th>
                    <th className="px-3 py-2 text-right">Utilisé</th>
                    <th className="px-3 py-2 text-right">Libre</th>
                    <th className="px-3 py-2 text-right">Total</th>
                    <th className="px-3 py-2 w-40">Usage</th>
                  </tr>
                </thead>
                <tbody>
                  {(server?.disks || []).map((d) => (
                    <tr key={`${d.device}-${d.mountpoint}`} className="border-t border-cp-border/70 dark:border-ink-800">
                      <td className="px-3 py-2.5 font-medium">{d.mountpoint}</td>
                      <td className="px-3 py-2.5 font-mono text-xs text-cp-muted">{d.device}</td>
                      <td className="px-3 py-2.5 text-cp-muted">{d.fstype}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatBytes(d.used)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatBytes(d.free)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatBytes(d.total)}</td>
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-cp-canvas dark:bg-ink-800">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${Math.min(100, d.percent)}%`,
                                backgroundColor: toneColor[tone(d.percent)],
                              }}
                            />
                          </div>
                          <span className="w-10 text-right text-xs tabular-nums text-cp-muted">
                            {d.percent.toFixed(0)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!server?.disks?.length && !isLoading ? (
                <EmptyState icon={<HardDrive className="h-5 w-5" />} message="Aucun volume monté détecté." />
              ) : null}
            </div>
          </SectionCard>
          {server?.disk_io ? (
            <div className="grid gap-3 sm:grid-cols-4">
              {[
                ["Lu", formatBytes(server.disk_io.read_bytes)],
                ["Écrit", formatBytes(server.disk_io.write_bytes)],
                ["Ops lecture", server.disk_io.read_count.toLocaleString("fr-FR")],
                ["Ops écriture", server.disk_io.write_count.toLocaleString("fr-FR")],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-xl border border-cp-border/70 bg-white px-3.5 py-3 dark:border-ink-700 dark:bg-ink-950">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">{label}</p>
                  <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {tab === "network" && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Reçu total", formatBytes(server?.network.bytes_recv)],
              ["Envoyé total", formatBytes(server?.network.bytes_sent)],
              ["Débit ↓", formatBps(server?.network.rates.recv_bps)],
              ["Débit ↑", formatBps(server?.network.rates.sent_bps)],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-xl border border-cp-border/70 bg-white px-3.5 py-3 dark:border-ink-700 dark:bg-ink-950">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">{label}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
              </div>
            ))}
          </div>
          <SectionCard title="Interfaces" icon={Network}>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
                  <tr>
                    <th className="px-3 py-2">Interface</th>
                    <th className="px-3 py-2">IP</th>
                    <th className="px-3 py-2">État</th>
                    <th className="px-3 py-2 text-right">↓</th>
                    <th className="px-3 py-2 text-right">↑</th>
                    <th className="px-3 py-2 text-right">Erreurs</th>
                    <th className="px-3 py-2 text-right">Drops</th>
                  </tr>
                </thead>
                <tbody>
                  {(server?.network.interfaces || []).map((iface) => (
                    <tr key={iface.name} className="border-t border-cp-border/70 dark:border-ink-800">
                      <td className="px-3 py-2.5 font-medium">
                        {iface.name}
                        {iface.speed_mbps ? (
                          <span className="ml-1.5 text-[11px] text-cp-muted">{iface.speed_mbps} Mb/s</span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs">{iface.ip || "—"}</td>
                      <td className="px-3 py-2.5">
                        <StatusDot status={iface.is_up ? "ok" : "error"} label={iface.is_up ? "UP" : "DOWN"} />
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatBytes(iface.bytes_recv)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatBytes(iface.bytes_sent)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{iface.errin + iface.errout}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{iface.dropin + iface.dropout}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </div>
      )}

      {tab === "processes" && (
        <SectionCard
          title="Top processus"
          icon={Activity}
          action={
            <div className="flex gap-1">
              <button
                type="button"
                className={procSort === "cpu" ? "vz-btn-primary vz-btn-sm" : "vz-btn-ghost vz-btn-sm"}
                onClick={() => setProcSort("cpu")}
              >
                CPU
              </button>
              <button
                type="button"
                className={procSort === "mem" ? "vz-btn-primary vz-btn-sm" : "vz-btn-ghost vz-btn-sm"}
                onClick={() => setProcSort("mem")}
              >
                RAM
              </button>
            </div>
          }
        >
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
                <tr>
                  <th className="px-3 py-2">PID</th>
                  <th className="px-3 py-2">Nom</th>
                  <th className="px-3 py-2">User</th>
                  <th className="px-3 py-2">État</th>
                  <th className="px-3 py-2 text-right">CPU %</th>
                  <th className="px-3 py-2 text-right">RAM %</th>
                </tr>
              </thead>
              <tbody>
                {(processes || []).map((p) => (
                  <tr key={`${p.pid}-${p.name}`} className="border-t border-cp-border/70 dark:border-ink-800">
                    <td className="px-3 py-2 font-mono text-xs text-cp-muted">{p.pid}</td>
                    <td className="px-3 py-2 font-medium">{p.name}</td>
                    <td className="px-3 py-2 text-cp-muted">{p.user}</td>
                    <td className="px-3 py-2 text-cp-muted">{p.status}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{p.cpu_percent.toFixed(1)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{p.memory_percent.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!processes?.length && !isLoading ? (
              <EmptyState icon={<Activity className="h-5 w-5" />} message="Aucun processus listé." />
            ) : null}
          </div>
        </SectionCard>
      )}

      {tab === "services" && (
        <SectionCard
          title="Santé des services"
          icon={Server}
          action={
            <Link to="/whm/monitoring" className="vz-btn-ghost vz-btn-sm">
              <Bell className="h-3.5 w-3.5" />
              Configurer les alertes
            </Link>
          }
        >
          {svcError ? (
            <p className="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
              {svcError}
            </p>
          ) : null}
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {(server?.services || []).map((s) => (
              <div
                key={s.name}
                className={`rounded-xl border px-3.5 py-3 ${
                  s.active
                    ? "border-cp-border/60 bg-cp-canvas/40 dark:border-ink-700 dark:bg-ink-900/40"
                    : "border-rose-200 bg-rose-50/80 dark:border-rose-900 dark:bg-rose-950/30"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-cp-text">{s.name}</p>
                    <p className="mt-0.5 text-[11px] text-cp-muted">
                      {s.unit ? `${s.unit}.service` : s.source || "process"}
                    </p>
                  </div>
                  <StatusDot status={s.active ? "ok" : "error"} label={s.active ? "Actif" : "Arrêté"} />
                </div>
                <div className="mt-2.5 flex items-center justify-end border-t border-cp-border/50 pt-2 dark:border-ink-800">
                  <ServiceActions
                    service={s}
                    busy={busyService === s.name}
                    onAction={onServiceAction}
                  />
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}
