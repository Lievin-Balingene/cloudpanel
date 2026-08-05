import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Rocket } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageChrome";

interface Overview {
  version: string;
  src_dir: string;
  src_exists: boolean;
  src_version: string;
  agent_installed: boolean;
  busy: boolean;
  recent_jobs: Array<{
    job_id: string;
    ok: boolean | null;
    pending?: boolean;
    error?: string;
    step?: string;
    version_before?: string;
    version_after?: string;
    finished_at?: string;
    started_at?: string;
  }>;
}

interface JobStatus {
  job_id: string;
  state: string;
  pending: boolean;
  ok: boolean | null;
  error: string;
  version_before: string;
  version_after: string;
  step: string;
  log: string;
  finished_at?: string;
  started_at?: string;
}

const STEP_LABELS: Record<string, string> = {
  queued: "En file d’attente…",
  starting: "Démarrage…",
  git_pull: "git pull…",
  git_pull_fallback: "git pull (secours)…",
  update_sh: "scripts/update.sh…",
  finished: "Terminé",
  failed: "Échec",
};

async function waitForApi(timeoutMs = 180_000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch("/api/v1/health/", { cache: "no-store" });
      if (res.ok) return true;
    } catch {
      /* API down during restart */
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  return false;
}

export function PanelUpdateManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [apiDown, setApiDown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLPreElement>(null);
  const activeRef = useRef(false);

  const { data: overview, isLoading } = useQuery({
    queryKey: ["panel-update-overview"],
    queryFn: () => apiRequest<Overview>("/server-setup/panel-update/"),
    refetchInterval: jobId && job?.pending ? false : 15_000,
  });

  const start = useMutation({
    mutationFn: () =>
      apiRequest<{ job_id: string; message: string }>("/server-setup/panel-update/start/", {
        method: "POST",
        body: JSON.stringify({ branch: "main" }),
      }),
    onSuccess: (data) => {
      setError(null);
      setJobId(data.job_id);
      setJob({
        job_id: data.job_id,
        state: "running",
        pending: true,
        ok: null,
        error: "",
        version_before: overview?.version || "",
        version_after: "",
        step: "queued",
        log: "",
      });
      void qc.invalidateQueries({ queryKey: ["panel-update-overview"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    activeRef.current = true;

    async function poll() {
      while (!cancelled && activeRef.current) {
        try {
          const data = await apiRequest<JobStatus>(`/server-setup/panel-update/jobs/${jobId}/`);
          if (cancelled) return;
          setApiDown(false);
          setJob(data);
          if (!data.pending) {
            activeRef.current = false;
            void qc.invalidateQueries({ queryKey: ["panel-update-overview"] });
            return;
          }
        } catch {
          if (cancelled) return;
          setApiDown(true);
          const up = await waitForApi(12_000);
          if (cancelled) return;
          if (!up) {
            // keep waiting in outer loop
          } else {
            setApiDown(false);
          }
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    }

    void poll();
    return () => {
      cancelled = true;
      activeRef.current = false;
    };
  }, [jobId, qc]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [job?.log]);

  const pendingJob = useMemo(
    () => overview?.recent_jobs?.find((j) => j.pending) || null,
    [overview],
  );

  useEffect(() => {
    if (!jobId && pendingJob?.job_id) {
      setJobId(pendingJob.job_id);
    }
  }, [jobId, pendingJob]);

  const canStart =
    !!overview?.agent_installed &&
    !!overview?.src_exists &&
    !overview?.busy &&
    !start.isPending &&
    !(job?.pending);

  return (
    <div className="space-y-3 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="git pull dans /opt/vzone-src puis scripts/update.sh — sans ouvrir SSH."
        actions={
          <button
            type="button"
            className="vz-btn-primary !px-3 !py-1.5 text-xs"
            disabled={!canStart}
            onClick={() => {
              if (
                window.confirm(
                  "Lancer la mise à jour du panel ? L’interface peut se déconnecter quelques minutes pendant le redémarrage de l’API.",
                )
              ) {
                start.mutate();
              }
            }}
          >
            {start.isPending || job?.pending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Rocket className="h-3.5 w-3.5" />
            )}
            Mettre à jour le panel
          </button>
        }
      />

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-cp-danger dark:border-red-900 dark:bg-red-950/30">
          {error}
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
                <dt className="text-cp-muted">Version panel</dt>
                <dd className="font-mono font-semibold">{overview?.version || "—"}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">VERSION source</dt>
                <dd className="font-mono">{overview?.src_version || "—"}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Dépôt</dt>
                <dd className="truncate font-mono text-[11px]" title={overview?.src_dir}>
                  {overview?.src_exists ? overview.src_dir : "absent"}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-cp-muted">Agent root</dt>
                <dd className={overview?.agent_installed ? "text-emerald-600" : "text-cp-danger"}>
                  {overview?.agent_installed ? "Installé" : "Manquant"}
                </dd>
              </div>
            </dl>
          )}

          {!overview?.agent_installed && (
            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              <p className="flex items-start gap-1.5 font-medium">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Première installation (une fois via SSH)
              </p>
              <pre className="mt-1.5 overflow-x-auto rounded bg-black/5 p-1.5 font-mono text-[10px] dark:bg-black/30">
                sudo bash /opt/vzone-src/scripts/install-update-agent.sh
              </pre>
              <p className="mt-1 text-cp-muted">
                Ensuite les mises à jour se font depuis cette page. Les prochains{" "}
                <code className="font-mono">update.sh</code> réinstallent l’agent automatiquement.
              </p>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-cp-border bg-white p-3 dark:border-ink-800 dark:bg-ink-950 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-cp-muted">
              Progression
            </p>
            {job?.pending && (
              <span className="inline-flex items-center gap-1 text-[11px] text-cp-orange">
                <Loader2 className="h-3 w-3 animate-spin" />
                {apiDown
                  ? "API redémarre — reconnexion…"
                  : STEP_LABELS[job.step] || job.step || "En cours…"}
              </span>
            )}
            {job && !job.pending && job.ok && (
              <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600">
                <CheckCircle2 className="h-3.5 w-3.5" />
                OK · {job.version_after || "à jour"}
              </span>
            )}
            {job && !job.pending && job.ok === false && (
              <span className="text-[11px] text-cp-danger">Échec · {job.error}</span>
            )}
          </div>

          <pre
            ref={logRef}
            className="mt-2 max-h-72 overflow-auto rounded-md bg-[#0f172a] p-2.5 font-mono text-[11px] leading-relaxed text-slate-200"
          >
            {job?.log ||
              (job?.pending
                ? "En attente des logs de l’agent…"
                : "Aucun job actif. Cliquez sur « Mettre à jour le panel ».")}
          </pre>

          {job && !job.pending && (
            <button
              type="button"
              className="vz-btn-ghost mt-2 !px-2 !py-1 text-[11px]"
              onClick={() => {
                setJobId(null);
                setJob(null);
                void qc.invalidateQueries({ queryKey: ["panel-update-overview"] });
              }}
            >
              <RefreshCw className="h-3 w-3" />
              Nouveau cycle
            </button>
          )}
        </div>
      </div>

      {!!overview?.recent_jobs?.length && (
        <div className="rounded-lg border border-cp-border bg-white dark:border-ink-800 dark:bg-ink-950">
          <div className="border-b border-cp-border px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-cp-muted dark:border-ink-800">
            Historique récent
          </div>
          <ul className="divide-y divide-cp-border text-xs dark:divide-ink-800">
            {overview.recent_jobs.map((j) => (
              <li key={j.job_id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <span className="font-mono text-[11px] text-cp-muted">{j.job_id.slice(0, 10)}…</span>
                <span>
                  {j.pending
                    ? `En cours · ${j.step || "…"}`
                    : j.ok
                      ? `${j.version_before || "?"} → ${j.version_after || "?"}`
                      : j.error || "Échec"}
                </span>
                <span className="text-[11px] text-cp-muted">{j.finished_at || j.started_at || ""}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
