import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Activity,
  Copy,
  Globe,
  Package,
  Pin,
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

function statusDot(percent: number | undefined) {
  if (percent == null || Number.isNaN(percent)) {
    return "bg-[#c5d0dc]";
  }
  if (percent >= 90) return "bg-red-500";
  if (percent >= 70) return "bg-amber-400";
  return "bg-emerald-500";
}

function loadTrend(load: number[] | null | undefined): string {
  if (!load || load.length < 3) return "—";
  const [a, b] = load;
  if (typeof a !== "number" || typeof b !== "number") return "—";
  if (a > b + 0.3) return "↑ Load Spike Settling";
  if (a < b - 0.3) return "↓ Load Decreasing";
  return "→ Load Stable";
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
      <div className="grid gap-6 xl:grid-cols-[1fr_300px]">
        {/* Colonne principale — Favorites style WHM */}
        <div className="min-w-0 space-y-5">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-[#2c3e50] dark:text-ink-50">
              Favorites
            </h1>
            <p className="mt-1 text-sm text-[#6b7c8f]">
              Raccourcis WHM — comptes, DNS, packages et supervision.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {favorites.map((tool) => (
              <Link
                key={tool.to}
                to={tool.to}
                className="group flex items-start gap-3 rounded-lg border border-[#c5d0dc] bg-white p-4 shadow-sm transition hover:border-[#a8b8c8] hover:shadow-md dark:border-ink-700 dark:bg-ink-950"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[#fff3ec] text-cp-orange">
                  <tool.icon className="h-5 w-5" />
                </span>
                <span className="min-w-0">
                  <span className="block text-[15px] font-semibold text-[#2c3e50] group-hover:text-cp-link dark:text-ink-50">
                    {tool.label}
                  </span>
                  <span className="mt-0.5 block text-xs leading-snug text-[#6b7c8f]">
                    {tool.desc}
                  </span>
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
                className="rounded-lg border border-[#c5d0dc] bg-white p-3 shadow-sm transition hover:border-cp-orange dark:border-ink-700 dark:bg-ink-950"
              >
                <p className="text-[10px] font-bold uppercase tracking-wide text-[#6b7c8f]">
                  {card.label}
                </p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-cp-orange">
                  {isLoading ? "…" : card.value}
                </p>
              </Link>
            ))}
          </div>

          {data?.services && data.services.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-[#c5d0dc] bg-white shadow-sm dark:border-ink-700 dark:bg-ink-950">
              <div className="border-b border-[#c5d0dc] bg-[#2a4a6b] px-4 py-2 text-xs font-bold uppercase tracking-wide text-white dark:border-ink-700">
                Service Status
              </div>
              <div className="grid gap-2 p-4 sm:grid-cols-2 lg:grid-cols-3">
                {data.services.map((svc) => (
                  <div
                    key={svc.name}
                    className="flex items-center justify-between rounded-md border border-[#e8eef4] px-3 py-2 text-sm dark:border-ink-700"
                  >
                    <span className="font-medium text-[#2c3e50] dark:text-ink-100">{svc.name}</span>
                    <span className={svc.active ? "text-cp-success" : "text-cp-danger"}>
                      {svc.active ? "up" : "down"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Colonne Statistics — style WHM cPanel */}
        <aside className="xl:sticky xl:top-4 xl:self-start">
          <div className="overflow-hidden rounded-lg border border-[#c5d0dc] bg-white shadow-sm dark:border-ink-700 dark:bg-ink-950">
            <div className="border-b border-[#e8eef4] px-4 py-3 dark:border-ink-800">
              <h2 className="text-lg font-semibold text-[#2c3e50] dark:text-ink-50">Statistics</h2>
            </div>

            <div className="divide-y divide-[#e8eef4] text-sm dark:divide-ink-800">
              <div className="px-4 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-[#8a9bb0]">
                  Hostname
                </p>
                <div className="mt-1 flex items-start gap-2">
                  <p className="min-w-0 flex-1 break-all font-medium text-[#2c3e50] dark:text-ink-100">
                    {isLoading ? "…" : hostname}
                  </p>
                  <button
                    type="button"
                    onClick={() => void copyHostname()}
                    className="shrink-0 rounded p-1 text-[#1a5fb4] hover:bg-[#e8f0fa]"
                    title="Copier"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                </div>
                {copied && <p className="mt-1 text-[10px] text-cp-success">Copié</p>}
              </div>

              <div className="px-4 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-[#8a9bb0]">
                  Server Monitoring
                </p>
                <ul className="mt-2 space-y-1.5">
                  <li className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${statusDot(m?.cpu.percent)}`} />
                    <span className="text-[#2c3e50] dark:text-ink-100">
                      CPU
                      {m ? (
                        <span className="ml-1 text-[#8a9bb0]">
                          {m.cpu.percent.toFixed(0)}%
                        </span>
                      ) : null}
                    </span>
                  </li>
                  <li className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${statusDot(m?.memory.percent)}`} />
                    <span className="text-[#2c3e50] dark:text-ink-100">
                      Memory
                      {m ? (
                        <span className="ml-1 text-[#8a9bb0]">
                          {m.memory.percent.toFixed(0)}%
                        </span>
                      ) : null}
                    </span>
                  </li>
                  <li className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${statusDot(m?.disk.percent)}`} />
                    <span className="text-[#2c3e50] dark:text-ink-100">
                      Disk
                      {m ? (
                        <span className="ml-1 text-[#8a9bb0]">
                          {m.disk.percent.toFixed(0)}% · {formatBytes(m.disk.used)}
                        </span>
                      ) : null}
                    </span>
                  </li>
                </ul>
              </div>

              <div className="px-4 py-3">
                <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-[#8a9bb0]">
                  <Pin className="h-3 w-3 text-[#1a5fb4]" />
                  Load Averages
                </p>
                <div className="mt-2 grid grid-cols-3 gap-2 text-center">
                  {[
                    { label: "1 min", value: load?.[0] },
                    { label: "5 min", value: load?.[1] },
                    { label: "15 min", value: load?.[2] },
                  ].map((col) => (
                    <div key={col.label}>
                      <p className="text-[10px] uppercase text-[#8a9bb0]">{col.label}</p>
                      <p className="mt-0.5 font-mono text-base font-semibold tabular-nums text-[#2c3e50] dark:text-ink-100">
                        {typeof col.value === "number" ? col.value.toFixed(2) : "—"}
                      </p>
                    </div>
                  ))}
                </div>
                <p className="mt-2 text-xs text-[#6b7c8f]">{loadTrend(load)}</p>
              </div>

              <div className="px-4 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-[#8a9bb0]">
                  Operating System
                </p>
                <p className="mt-1 font-medium leading-snug text-[#2c3e50] dark:text-ink-100">
                  {stats?.operating_system || "—"}
                </p>
              </div>

              <div className="px-4 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-[#8a9bb0]">
                  Product
                </p>
                <p className="mt-1 font-medium text-[#2c3e50] dark:text-ink-100">
                  {stats?.product || "V-zone WHM"}
                </p>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
