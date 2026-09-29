import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, RefreshCw } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { EmptyState, PageHeader } from "@/components/ui/PageChrome";

interface Hit {
  ip: string;
  method: string;
  path: string;
  status: number;
  time: string;
}

interface VisitorsMetrics {
  visits: number;
  unique_ips: number;
  top_paths: { path: string; hits: number }[];
  top_ips: { ip: string; hits: number }[];
  recent: Hit[];
  errors_sample: Hit[];
  note?: string;
}

function formatTime(value: string) {
  return new Date(value).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Ranking({
  title,
  rows,
  valueKey,
}: {
  title: string;
  rows: ({ hits: number } & Record<string, string | number>)[];
  valueKey: "path" | "ip";
}) {
  return (
    <div className="vz-panel overflow-hidden">
      <h2 className="border-b border-cp-border px-4 py-3 text-sm font-semibold text-cp-text dark:border-ink-800">{title}</h2>
      {rows.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-cp-muted">Aucune donnée.</p>
      ) : (
        <div className="divide-y divide-cp-border dark:divide-ink-800">
          {rows.map((row) => (
            <div key={String(row[valueKey])} className="flex items-center justify-between gap-3 px-4 py-2.5">
              <span className="truncate font-mono text-xs text-cp-text">{row[valueKey]}</span>
              <span className="shrink-0 text-xs font-semibold tabular-nums text-cp-muted">{row.hits}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function HitsTable({ title, rows }: { title: string; rows: Hit[] }) {
  return (
    <div className="vz-panel overflow-hidden">
      <h2 className="border-b border-cp-border px-4 py-3 text-sm font-semibold text-cp-text dark:border-ink-800">{title}</h2>
      {rows.length === 0 ? (
        <EmptyState icon={<Activity className="h-5 w-5" />} message="Aucune requête sur cette période." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-cp-canvas/60 text-xs text-cp-muted dark:bg-ink-900/60">
              <tr><th className="px-4 py-2">Date</th><th className="px-4 py-2">IP</th><th className="px-4 py-2">Requête</th><th className="px-4 py-2">Statut</th></tr>
            </thead>
            <tbody className="divide-y divide-cp-border dark:divide-ink-800">
              {rows.map((row, index) => (
                <tr key={`${row.time}-${row.ip}-${index}`}>
                  <td className="whitespace-nowrap px-4 py-2.5 text-xs text-cp-muted">{formatTime(row.time)}</td>
                  <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">{row.ip}</td>
                  <td className="max-w-md truncate px-4 py-2.5 font-mono text-xs">{row.method} {row.path}</td>
                  <td className={`px-4 py-2.5 font-semibold ${row.status >= 400 ? "text-rose-600" : "text-emerald-600"}`}>{row.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function MetricsVisitorsManager({ title }: { title: string }) {
  const query = useQuery({
    queryKey: ["metrics-visitors", 24],
    queryFn: () => apiRequest<VisitorsMetrics>("/dashboard/metrics/visitors/?hours=24"),
  });
  const metrics = query.data;

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Trafic observé dans les journaux web de vos domaines pendant les dernières 24 heures."
        stats={[
          { label: "Visites", value: metrics?.visits ?? "—" },
          { label: "IP uniques", value: metrics?.unique_ips ?? "—" },
          { label: "Erreurs", value: metrics?.errors_sample.length ?? "—" },
        ]}
        actions={
          <button type="button" className="vz-btn-ghost" onClick={() => void query.refetch()}>
            <RefreshCw className={`h-4 w-4 ${query.isFetching ? "animate-spin" : ""}`} />
            Actualiser
          </button>
        }
      />
      {metrics?.note && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          {metrics.note}
        </div>
      )}
      {query.error && <p className="text-sm text-rose-600">{query.error.message}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Ranking title="Pages les plus visitées" rows={metrics?.top_paths ?? []} valueKey="path" />
        <Ranking title="Adresses IP principales" rows={metrics?.top_ips ?? []} valueKey="ip" />
      </div>
      <HitsTable title="Requêtes récentes" rows={metrics?.recent ?? []} />
      <div className="flex items-center gap-2 text-sm font-semibold text-cp-text">
        <AlertTriangle className="h-4 w-4 text-rose-500" />
        Échantillon des erreurs
      </div>
      <HitsTable title="Erreurs HTTP" rows={metrics?.errors_sample ?? []} />
    </div>
  );
}
