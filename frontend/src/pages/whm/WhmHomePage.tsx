import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Activity,
  Check,
  Copy,
  Cpu,
  Globe,
  HardDrive,
  MemoryStick,
  Package,
  Server,
  UserPlus,
  Users,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { DashboardOverview } from "@/types";
import { formatBytes } from "@/lib/format";
import { useState } from "react";

const favorites = [
  {
    to: "/whm/accounts",
    label: "List Accounts",
    desc: "View, modify, and manage hosting accounts.",
    icon: Users,
  },
  {
    to: "/whm/accounts/create",
    label: "Create a New Account",
    desc: "Domain + username + package",
    icon: UserPlus,
  },
  {
    to: "/whm/server-setup",
    label: "Basic Setup",
    desc: "Hostname & nameservers",
    icon: Server,
  },
  {
    to: "/whm/packages",
    label: "Packages",
    desc: "Hosting plans and limits",
    icon: Package,
  },
  {
    to: "/whm/dns",
    label: "DNS Functions",
    desc: "Zones & DNS records",
    icon: Globe,
  },
  {
    to: "/whm/resources",
    label: "Server Information",
    desc: "CPU, RAM, disk details",
    icon: Activity,
  },
];

function tone(percent: number | undefined): "ok" | "warn" | "bad" | "idle" {
  if (percent == null || Number.isNaN(percent)) return "idle";
  if (percent >= 90) return "bad";
  if (percent >= 70) return "warn";
  return "ok";
}

const toneDot: Record<string, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-400",
  bad: "bg-rose-500",
  idle: "bg-slate-300",
};

const toneBar: Record<string, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-400",
  bad: "bg-rose-500",
  idle: "bg-slate-300",
};

function loadTrend(load: number[] | null | undefined): { label: string; up: boolean | null } {
  if (!load || load.length < 2) return { label: "En attente…", up: null };
  const [a, b] = load;
  if (typeof a !== "number" || typeof b !== "number") return { label: "—", up: null };
  if (a > b + 0.3) return { label: "Load spike settling", up: true };
  if (a < b - 0.3) return { label: "Load decreasing", up: false };
  return { label: "Load stable", up: null };
}

function MetricRow({
  icon: Icon,
  label,
  percent,
  hint,
}: {
  icon: typeof Cpu;
  label: string;
  percent?: number;
  hint?: string;
}) {
  const t = tone(percent);
  const pct = typeof percent === "number" ? Math.min(100, Math.max(0, percent)) : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[13px] text-slate-700 dark:text-ink-100">
          <span className={`h-2 w-2 shrink-0 rounded-full ${toneDot[t]}`} />
          <Icon className="h-3.5 w-3.5 text-slate-400" />
          <span className="font-medium">{label}</span>
        </div>
        <span className="tabular-nums text-[12px] font-semibold text-slate-600 dark:text-ink-200">
          {typeof percent === "number" ? `${percent.toFixed(0)}%` : "—"}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-ink-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${toneBar[t]}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {hint ? <p className="text-[11px] text-slate-400">{hint}</p> : null}
    </div>
  );
}

export function WhmHomePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiRequest<DashboardOverview>("/dashboard/overview/"),
    refetchInterval: 10000,
  });
  const [copied, setCopied] = useState(false);

  const m = data?.metrics;
  const stats = data?.statistics;
  const load = m?.load_average;
  const hostname = stats?.hostname || "—";
  const trend = loadTrend(load);

  async function copyHostname() {
    try {
      await navigator.clipboard.writeText(hostname);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="animate-fade-up">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-5">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-800 dark:text-ink-50">
              Favorites
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Raccourcis Admin — comptes, DNS, packages et supervision.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {favorites.map((tool) => (
              <Link
                key={tool.to}
                to={tool.to}
                className="group flex items-start gap-3 rounded-xl border border-slate-200/90 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md dark:border-ink-700 dark:bg-ink-950"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-orange-50 text-cp-orange dark:bg-orange-950/40">
                  <tool.icon className="h-5 w-5" />
                </span>
                <span className="min-w-0">
                  <span className="block text-[15px] font-semibold text-slate-800 group-hover:text-cp-link dark:text-ink-50">
                    {tool.label}
                  </span>
                  <span className="mt-0.5 block text-xs leading-snug text-slate-500">{tool.desc}</span>
                </span>
              </Link>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Accounts", value: data?.users_total ?? "—", to: "/whm/accounts" },
              { label: "Domains", value: data?.domains_total ?? "—", to: "/whm/domains" },
              { label: "Packages", value: data?.packages_active ?? "—", to: "/whm/packages" },
              { label: "DNS Zones", value: data?.dns_zones ?? "—", to: "/whm/dns" },
            ].map((card) => (
              <Link
                key={card.label}
                to={card.to}
                className="rounded-xl border border-slate-200/90 bg-white p-3.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:border-cp-orange/50 dark:border-ink-700 dark:bg-ink-950"
              >
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  {card.label}
                </p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-cp-orange">
                  {isLoading ? "…" : card.value}
                </p>
              </Link>
            ))}
          </div>

          {data?.services && data.services.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-ink-700 dark:bg-ink-950">
              <div className="border-b border-slate-100 px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:border-ink-800">
                Service Status
              </div>
              <div className="grid gap-2 p-4 sm:grid-cols-2 lg:grid-cols-3">
                {data.services.map((svc) => (
                  <div
                    key={svc.name}
                    className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm dark:bg-ink-900"
                  >
                    <span className="font-medium text-slate-700 dark:text-ink-100">{svc.name}</span>
                    <span
                      className={`inline-flex items-center gap-1 text-xs font-semibold ${
                        svc.active ? "text-emerald-600" : "text-rose-600"
                      }`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          svc.active ? "bg-emerald-500" : "bg-rose-500"
                        }`}
                      />
                      {svc.active ? "up" : "down"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Statistics — carte soignée */}
        <aside className="xl:sticky xl:top-4 xl:self-start">
          <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_8px_30px_rgba(15,23,42,0.06)] dark:border-ink-700 dark:bg-ink-950">
            <div className="relative overflow-hidden bg-gradient-to-br from-[#2a4a6b] via-[#345578] to-[#1e3a55] px-5 py-4 text-white">
              <div
                className="pointer-events-none absolute -right-6 -top-8 h-28 w-28 rounded-full bg-white/10"
                aria-hidden
              />
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/70">
                Server
              </p>
              <h2 className="mt-0.5 text-xl font-semibold tracking-tight">Statistics</h2>
            </div>

            <div className="space-y-5 p-5">
              <section>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Hostname
                </p>
                <div className="mt-1.5 flex items-start gap-2 rounded-xl bg-slate-50 px-3 py-2.5 dark:bg-ink-900">
                  <p className="min-w-0 flex-1 break-all text-[13px] font-semibold leading-snug text-slate-800 dark:text-ink-50">
                    {isLoading ? "…" : hostname}
                  </p>
                  <button
                    type="button"
                    onClick={() => void copyHostname()}
                    className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-cp-link hover:text-cp-link dark:border-ink-600 dark:bg-ink-950"
                    title="Copier"
                  >
                    {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                </div>
              </section>

              <section>
                <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Server Monitoring
                </p>
                <div className="space-y-3.5">
                  <MetricRow icon={Cpu} label="CPU" percent={m?.cpu.percent} />
                  <MetricRow
                    icon={MemoryStick}
                    label="Memory"
                    percent={m?.memory.percent}
                    hint={
                      m
                        ? `${formatBytes(m.memory.used)} / ${formatBytes(m.memory.total)}`
                        : undefined
                    }
                  />
                  <MetricRow
                    icon={HardDrive}
                    label="Disk"
                    percent={m?.disk.percent}
                    hint={m ? formatBytes(m.disk.used) : undefined}
                  />
                </div>
              </section>

              <section>
                <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Load Averages
                </p>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { label: "1 min", value: load?.[0] },
                    { label: "5 min", value: load?.[1] },
                    { label: "15 min", value: load?.[2] },
                  ].map((col) => (
                    <div
                      key={col.label}
                      className="rounded-xl border border-slate-100 bg-slate-50 px-2 py-2.5 text-center dark:border-ink-700 dark:bg-ink-900"
                    >
                      <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
                        {col.label}
                      </p>
                      <p className="mt-1 font-mono text-[15px] font-semibold tabular-nums text-slate-800 dark:text-ink-50">
                        {typeof col.value === "number" ? col.value.toFixed(2) : "—"}
                      </p>
                    </div>
                  ))}
                </div>
                <p
                  className={`mt-2.5 text-xs font-medium ${
                    trend.up === true
                      ? "text-amber-600"
                      : trend.up === false
                        ? "text-emerald-600"
                        : "text-slate-500"
                  }`}
                >
                  {trend.up === true ? "↑ " : trend.up === false ? "↓ " : "→ "}
                  {trend.label}
                </p>
              </section>

              <section className="space-y-3 border-t border-slate-100 pt-4 dark:border-ink-800">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Operating System
                  </p>
                  <p className="mt-1 text-[13px] font-medium leading-snug text-slate-700 dark:text-ink-100">
                    {stats?.operating_system || "—"}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Product
                  </p>
                  <p className="mt-1 text-[13px] font-medium text-slate-700 dark:text-ink-100">
                    {stats?.product || "V-zone Admin"}
                  </p>
                </div>
              </section>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
