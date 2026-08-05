import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Server } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageChrome";

interface OlsOverview {
  enabled: boolean;
  installed: boolean;
  active: boolean;
  listen: string;
  version: string;
  vhosts: number;
  domains_ols: number;
  data_dir: string;
  maps_file: string;
  hint: string | null;
}

export function OlsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["ols-overview"],
    queryFn: () => apiRequest<OlsOverview>("/server-setup/ols/"),
    refetchInterval: 15_000,
  });

  const reload = useMutation({
    mutationFn: () =>
      apiRequest<{ reloaded: boolean; vhosts: number }>("/server-setup/ols/reload/", {
        method: "POST",
        body: "{}",
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["ols-overview"] }),
  });

  const ready = Boolean(data?.enabled && data?.installed);

  return (
    <div className="space-y-3 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Moteur PHP/WordPress optionnel derrière Nginx (ports 80/443 inchangés)."
        actions={
          <button
            type="button"
            className="vz-btn-primary !px-3 !py-1.5 text-xs"
            disabled={!ready || reload.isPending}
            onClick={() => reload.mutate()}
          >
            {reload.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Reload OLS
          </button>
        }
      />

      {(error as Error | null) && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-cp-danger">
          {(error as Error).message}
        </p>
      )}

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="rounded-lg border border-cp-border bg-white p-3 dark:border-ink-800 dark:bg-ink-950 lg:col-span-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-cp-muted">État</p>
          {isLoading ? (
            <p className="mt-2 text-xs text-cp-muted">Chargement…</p>
          ) : (
            <dl className="mt-2 space-y-2 text-xs">
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Activé (env)</dt>
                <dd className={data?.enabled ? "text-emerald-600" : "text-cp-muted"}>
                  {data?.enabled ? "oui" : "non"}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Installé</dt>
                <dd className={data?.installed ? "text-emerald-600" : "text-cp-danger"}>
                  {data?.installed ? "oui" : "non"}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Service</dt>
                <dd className="inline-flex items-center gap-1">
                  {data?.active ? (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> actif
                    </>
                  ) : (
                    "inactif"
                  )}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Listen</dt>
                <dd className="font-mono">{data?.listen || "—"}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Domaines OLS</dt>
                <dd className="font-semibold">{data?.domains_ols ?? "—"}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Vhosts</dt>
                <dd>{data?.vhosts ?? "—"}</dd>
              </div>
            </dl>
          )}
        </div>

        <div className="rounded-lg border border-cp-border bg-white p-3 dark:border-ink-800 dark:bg-ink-950 lg:col-span-2">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-cp-muted">
            <Server className="h-3.5 w-3.5" />
            Architecture
          </p>
          <p className="mt-2 text-xs text-cp-muted">
            Nginx reste sur <strong className="text-cp-text">:80/:443</strong> (panel, SSL, ACME,
            Python/Node). OpenLiteSpeed écoute en local et sert uniquement les domaines dont le{" "}
            <em>web engine</em> est « OpenLiteSpeed » (PHP / WordPress / static).
          </p>
          {data?.version && (
            <pre className="mt-3 overflow-x-auto rounded bg-cp-canvas p-2 font-mono text-[11px] dark:bg-ink-900">
              {data.version}
            </pre>
          )}
          {data?.hint && (
            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              <p className="flex items-start gap-1.5 font-medium">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Activation
              </p>
              <pre className="mt-1.5 overflow-x-auto rounded bg-black/5 p-1.5 font-mono text-[10px] dark:bg-black/30">
                {`# /etc/vzone/vzone.env
VZONE_OLS_ENABLED=1

sudo bash /opt/vzone-src/scripts/install-openlitespeed.sh
# ou : Panel Update après git pull`}
              </pre>
              <p className="mt-1 text-cp-muted">{data.hint}</p>
            </div>
          )}
          {reload.isError && (
            <p className="mt-2 text-xs text-cp-danger">{(reload.error as Error).message}</p>
          )}
          {reload.isSuccess && (
            <p className="mt-2 text-xs text-emerald-600">Reload OLS OK.</p>
          )}
        </div>
      </div>
    </div>
  );
}
