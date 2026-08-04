import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Activity,
  Globe,
  Package,
  Server,
  UserPlus,
  Users,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { DashboardOverview } from "@/types";
import { formatBytes } from "@/lib/format";

const tools = [
  {
    to: "/whm/accounts/create",
    label: "Create a New Account",
    desc: "Domain + username + package",
    icon: UserPlus,
  },
  {
    to: "/whm/accounts",
    label: "List Accounts",
    desc: "Modify, suspend, terminate",
    icon: Users,
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
    desc: "Hosting plans",
    icon: Package,
  },
  {
    to: "/whm/dns",
    label: "DNS Functions",
    desc: "Zones & records",
    icon: Globe,
  },
  {
    to: "/whm/resources",
    label: "Server Information",
    desc: "CPU, RAM, disk",
    icon: Activity,
  },
];

export function WhmHomePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiRequest<DashboardOverview>("/dashboard/overview/"),
    refetchInterval: 10000,
  });

  return (
    <div className="space-y-5 animate-fade-up">
      <div className="whm-page-head">
        <div className="whm-page-head-bar">
          <h1 className="text-sm font-semibold uppercase tracking-wide">WHM Home</h1>
        </div>
        <p className="px-4 py-3 text-sm text-cp-muted">
          Web Host Manager — comptes, domaines, packages et supervision serveur.
        </p>
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
            className="vz-panel block p-4 transition hover:border-cp-orange hover:shadow-md"
          >
            <p className="text-[11px] font-bold uppercase tracking-wide text-cp-muted">{card.label}</p>
            <p className="mt-2 text-3xl font-semibold tabular-nums text-cp-orange">
              {isLoading ? "…" : card.value}
            </p>
          </Link>
        ))}
      </div>

      <div>
        <h2 className="mb-3 text-xs font-bold uppercase tracking-wider text-cp-muted">
          Tools
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {tools.map((tool) => (
            <Link key={tool.to} to={tool.to} className="cp-tool !items-start !text-left">
              <div className="flex w-full items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-cp-orange-soft text-cp-orange">
                  <tool.icon className="h-5 w-5" />
                </span>
                <span>
                  <span className="block text-sm font-semibold text-cp-navy dark:text-ink-50">
                    {tool.label}
                  </span>
                  <span className="mt-0.5 block text-xs text-cp-muted">{tool.desc}</span>
                </span>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {data?.metrics && (
        <div className="grid gap-3 lg:grid-cols-3">
          <Stat title="CPU" value={`${data.metrics.cpu.percent.toFixed(1)}%`} />
          <Stat
            title="Memory"
            value={`${data.metrics.memory.percent.toFixed(1)}%`}
            hint={`${formatBytes(data.metrics.memory.used)} / ${formatBytes(data.metrics.memory.total)}`}
          />
          <Stat
            title="Disk"
            value={`${data.metrics.disk.percent.toFixed(1)}%`}
            hint={formatBytes(data.metrics.disk.used)}
          />
        </div>
      )}

      {data?.services && data.services.length > 0 && (
        <div className="vz-panel overflow-hidden p-0">
          <div className="border-b border-cp-border bg-cp-header px-4 py-2 text-xs font-bold uppercase tracking-wide text-white dark:border-ink-800">
            Service Status
          </div>
          <div className="grid gap-2 p-4 sm:grid-cols-2 lg:grid-cols-4">
            {data.services.map((svc) => (
              <div
                key={svc.name}
                className="flex items-center justify-between rounded-md border border-cp-border px-3 py-2 text-sm dark:border-ink-700"
              >
                <span className="font-medium">{svc.name}</span>
                <span className={svc.active ? "text-cp-success" : "text-cp-danger"}>
                  {svc.active ? "up" : "down"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ title, value, hint }: { title: string; value: string; hint?: string }) {
  return (
    <div className="vz-panel p-4">
      <p className="text-[11px] font-bold uppercase text-cp-muted">{title}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint ? <p className="mt-1 text-xs text-cp-muted">{hint}</p> : null}
    </div>
  );
}
