import { useQuery } from "@tanstack/react-query";
import { HardDrive, Mail, Database, Globe, Upload, Package } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import type { DashboardOverview } from "@/types";

interface Assignment {
  package: {
    name: string;
    disk_mb: number;
    bandwidth_mb: number;
    domains: number;
    emails: number;
    databases: number;
    ftp_accounts: number;
    python_apps: number;
    node_apps: number;
    docker_containers: number;
    allow_backup: boolean;
    unlimited_disk: boolean;
    unlimited_bandwidth: boolean;
  };
}

function QuotaCard({
  icon: Icon,
  label,
  used,
  limit,
  unlimited,
  unit,
}: {
  icon: typeof Package;
  label: string;
  used?: number;
  limit?: number;
  unlimited?: boolean;
  unit?: string;
}) {
  const u = used ?? 0;
  const lim = limit ?? 0;
  const pct = unlimited || lim <= 0 ? 0 : Math.min(100, (u / lim) * 100);
  const value = unlimited
    ? `${u}${unit ? ` ${unit}` : ""} / Illimité`
    : `${u} / ${lim}${unit ? ` ${unit}` : ""}`;

  return (
    <div className="rounded-xl border border-cp-border/70 bg-cp-canvas/60 p-3.5 dark:border-ink-700 dark:bg-ink-900/50">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-cp-orange shadow-sm dark:bg-ink-950">
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-cp-muted">{label}</p>
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-cp-text">{value}</p>
          {!unlimited && lim > 0 && (
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#e2e8f0] dark:bg-ink-800">
              <div
                className={`h-full rounded-full ${
                  pct >= 90 ? "bg-cp-danger" : pct >= 70 ? "bg-amber-500" : "bg-cp-orange"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function ClientPackagePage() {
  const user = useAuthStore((s) => s.user);
  const { data, isLoading } = useQuery({
    queryKey: ["package-mine"],
    queryFn: () => apiRequest<Assignment | null>("/packages/mine/"),
  });
  const { data: overview } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiRequest<DashboardOverview>("/dashboard/overview/"),
  });

  if (isLoading) {
    return <div className="vz-panel p-5 text-sm text-cp-muted">Chargement de votre forfait…</div>;
  }

  if (!data) {
    return (
      <div className="vz-panel p-6">
        <h1 className="text-xl font-semibold">Mon forfait</h1>
        <p className="mt-2 text-sm text-cp-muted">
          Aucun forfait n’est encore associé à votre compte. Contactez le support si besoin.
        </p>
      </div>
    );
  }

  const pkg = data.package;
  const usage = overview?.usage;
  const diskUsedMb =
    typeof overview?.disk?.used_mb === "number" ? overview.disk.used_mb : 0;

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel overflow-hidden">
        <div className="bg-gradient-to-r from-[#1e3a5f] to-[#2a4a6b] px-4 py-5 text-white sm:px-5">
          <div className="flex flex-wrap items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/15">
              <Package className="h-5 w-5" />
            </span>
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-white/70">Votre forfait</p>
              <h1 className="text-xl font-semibold">{pkg.name}</h1>
              <p className="text-sm text-white/80">
                Compte <strong className="text-white">{user?.username}</strong>
              </p>
            </div>
          </div>
        </div>

        <div className="grid gap-3 p-3 sm:grid-cols-2 sm:p-4 lg:grid-cols-3">
          <QuotaCard
            icon={HardDrive}
            label="Espace disque"
            used={Math.round(diskUsedMb * 10) / 10}
            limit={pkg.disk_mb}
            unlimited={pkg.unlimited_disk}
            unit="Mo"
          />
          <QuotaCard
            icon={Globe}
            label="Domaines"
            used={usage?.domains ?? overview?.domains_total ?? 0}
            limit={pkg.domains}
          />
          <QuotaCard
            icon={Mail}
            label="Boîtes mail"
            used={usage?.emails ?? 0}
            limit={pkg.emails}
          />
          <QuotaCard
            icon={Database}
            label="Bases de données"
            used={usage?.databases ?? 0}
            limit={pkg.databases}
          />
          <QuotaCard
            icon={Upload}
            label="Comptes FTP"
            used={usage?.ftp_accounts ?? 0}
            limit={pkg.ftp_accounts}
          />
          <QuotaCard
            icon={HardDrive}
            label="Bande passante / mois"
            used={0}
            limit={pkg.bandwidth_mb}
            unlimited={pkg.unlimited_bandwidth}
            unit="Mo"
          />
        </div>
      </div>

      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border bg-[#f0f4f8] px-4 py-2.5 dark:border-ink-800 dark:bg-ink-900">
          <h2 className="text-sm font-semibold text-cp-text">Inclus dans le forfait</h2>
        </div>
        <ul className="divide-y divide-cp-border text-sm dark:divide-ink-800">
          {[
            ["Applications Python", String(pkg.python_apps)],
            ["Applications Node.js", String(pkg.node_apps)],
            ["Conteneurs Docker", pkg.docker_containers > 0 ? String(pkg.docker_containers) : "Non inclus"],
            ["Sauvegardes", pkg.allow_backup ? "Autorisées" : "Non disponibles"],
          ].map(([k, v]) => (
            <li key={k} className="flex items-center justify-between gap-3 px-4 py-3">
              <span className="text-cp-muted">{k}</span>
              <span className="font-medium text-cp-text">{v}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
