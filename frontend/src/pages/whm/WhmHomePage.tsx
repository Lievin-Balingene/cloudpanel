import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiRequest } from "@/lib/api";
import type { DashboardOverview } from "@/types";
import { formatBytes } from "@/lib/format";

export function WhmHomePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiRequest<DashboardOverview>("/dashboard/overview/"),
    refetchInterval: 10000,
  });

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold text-cp-text dark:text-ink-50">Accueil WHM</h1>
        <p className="mt-1 text-sm text-cp-muted">
          Supervision serveur, comptes d&apos;hébergement, packages et DNS.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Comptes", value: data?.users_total ?? "—", to: "/whm/accounts" },
          { label: "Domaines", value: data?.domains_total ?? "—", to: "/whm/domains" },
          { label: "Packages", value: data?.packages_active ?? "—", to: "/whm/packages" },
          { label: "Zones DNS", value: data?.dns_zones ?? "—", to: "/whm/dns" },
        ].map((card) => (
          <Link key={card.label} to={card.to} className="vz-panel block p-4 hover:border-cp-orange">
            <p className="text-xs font-semibold uppercase tracking-wide text-cp-muted">{card.label}</p>
            <p className="mt-2 text-3xl font-semibold text-cp-orange">{isLoading ? "…" : card.value}</p>
          </Link>
        ))}
      </div>

      {data?.metrics && (
        <div className="grid gap-3 lg:grid-cols-3">
          <Stat title="CPU" value={`${data.metrics.cpu.percent.toFixed(1)}%`} />
          <Stat
            title="Mémoire"
            value={`${data.metrics.memory.percent.toFixed(1)}%`}
            hint={`${formatBytes(data.metrics.memory.used)} / ${formatBytes(data.metrics.memory.total)}`}
          />
          <Stat
            title="Disque"
            value={`${data.metrics.disk.percent.toFixed(1)}%`}
            hint={formatBytes(data.metrics.disk.used)}
          />
        </div>
      )}

      {data?.services && data.services.length > 0 && (
        <div className="vz-panel p-4">
          <h2 className="mb-3 font-semibold">Services</h2>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {data.services.map((svc) => (
              <div
                key={svc.name}
                className="flex items-center justify-between rounded border border-cp-border px-3 py-2 text-sm dark:border-ink-700"
              >
                <span className="font-medium">{svc.name}</span>
                <span className={svc.active ? "text-cp-success" : "text-cp-danger"}>
                  {svc.active ? "actif" : "down"}
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
      <p className="text-xs font-semibold uppercase text-cp-muted">{title}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {hint ? <p className="mt-1 text-xs text-cp-muted">{hint}</p> : null}
    </div>
  );
}
