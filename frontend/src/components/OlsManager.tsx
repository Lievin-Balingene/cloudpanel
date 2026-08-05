import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Server, Zap } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageChrome";

interface OlsOverview {
  enabled: boolean;
  enabled_mode?: string;
  installed: boolean;
  ready?: boolean;
  active: boolean;
  listen: string;
  version: string;
  vhosts: number;
  domains_ols: number;
  domains_nginx?: number;
  default_engine?: string;
  data_dir: string;
  maps_file: string;
  hint: string | null;
  status_message?: string;
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

  const adopt = useMutation({
    mutationFn: () =>
      apiRequest<{ updated: number; skipped: number }>("/server-setup/ols/adopt/", {
        method: "POST",
        body: "{}",
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["ols-overview"] }),
  });

  const ready = Boolean(data?.ready ?? (data?.enabled && data?.installed));
  const canReload = Boolean(data?.installed);

  return (
    <div className="space-y-3 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Comme cPanel : sites PHP/WordPress servis par OpenLiteSpeed (Nginx garde le panel + SSL)."
        actions={
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              className="vz-btn-primary !px-3 !py-1.5 text-xs"
              disabled={!ready || adopt.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    "Passer tous les domaines PHP/static existants en OpenLiteSpeed ?",
                  )
                ) {
                  adopt.mutate();
                }
              }}
            >
              {adopt.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Zap className="h-3.5 w-3.5" />
              )}
              Activer OLS sur les domaines
            </button>
            <button
              type="button"
              className="vz-btn-ghost !px-3 !py-1.5 text-xs"
              disabled={!canReload || reload.isPending}
              title={!canReload ? "OpenLiteSpeed n'est pas installé" : "Recharger OpenLiteSpeed"}
              onClick={() => reload.mutate()}
            >
              {reload.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              Reload
            </button>
          </div>
        }
      />

      {(error as Error | null) && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-cp-danger">
          {(error as Error).message}
        </p>
      )}

      {data?.status_message && (
        <div
          className={`rounded-lg border px-3 py-2 text-xs ${
            ready
              ? "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200"
              : "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/30"
          }`}
        >
          {ready ? (
            <span className="inline-flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {data.status_message}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5" />
              {data.status_message}
            </span>
          )}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="rounded-lg border border-cp-border bg-white p-3 dark:border-ink-800 dark:bg-ink-950 lg:col-span-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-cp-muted">État</p>
          {isLoading ? (
            <p className="mt-2 text-xs text-cp-muted">Chargement…</p>
          ) : (
            <dl className="mt-2 space-y-2 text-xs">
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Prêt</dt>
                <dd className={ready ? "font-semibold text-emerald-600" : "text-cp-danger"}>
                  {ready ? "oui" : "non"}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Mode</dt>
                <dd className="font-mono">{data?.enabled_mode || "—"}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Service</dt>
                <dd>
                  {data?.active ? (
                    <span className="inline-flex items-center gap-1 text-emerald-600">
                      <CheckCircle2 className="h-3.5 w-3.5" /> actif
                    </span>
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
                <dt className="text-cp-muted">Nouveaux domaines</dt>
                <dd className="font-medium">
                  {data?.default_engine === "ols" ? "→ OpenLiteSpeed" : "→ Nginx"}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Domaines OLS</dt>
                <dd className="font-semibold">{data?.domains_ols ?? "—"}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Encore en Nginx</dt>
                <dd>{data?.domains_nginx ?? "—"}</dd>
              </div>
            </dl>
          )}
        </div>

        <div className="rounded-lg border border-cp-border bg-white p-3 dark:border-ink-800 dark:bg-ink-950 lg:col-span-2">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-cp-muted">
            <Server className="h-3.5 w-3.5" />
            Comment ça marche
          </p>
          <ul className="mt-2 list-disc space-y-1.5 pl-4 text-xs text-cp-muted">
            <li>
              <strong className="text-cp-text">Nginx</strong> reste sur :80/:443 (panel, SSL, ACME,
              Python, Node).
            </li>
            <li>
              <strong className="text-cp-text">OpenLiteSpeed</strong> écoute en local (
              {data?.listen || "127.0.0.1:8088"}) et sert les sites PHP/WordPress.
            </li>
            <li>
              À la création d&apos;un domaine/sous-domaine, le moteur est{" "}
              <strong className="text-cp-text">OpenLiteSpeed par défaut</strong> (si prêt).
            </li>
            <li>
              Les domaines déjà créés en Nginx : cliquez{" "}
              <em>« Activer OLS sur les domaines »</em>.
            </li>
          </ul>
          {data?.version && !data.version.includes("Usage:") && (
            <p className="mt-3 font-mono text-[11px] text-cp-muted">Version : {data.version}</p>
          )}
          {data?.hint && (
            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              <p className="font-medium">{data.hint}</p>
            </div>
          )}
          {adopt.isSuccess && (
            <p className="mt-2 text-xs text-emerald-600">
              Domaines migrés vers OLS : {(adopt.data as { updated?: number })?.updated ?? "OK"}
            </p>
          )}
          {(adopt.isError || reload.isError) && (
            <p className="mt-2 text-xs text-cp-danger">
              {((adopt.error || reload.error) as Error).message}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
