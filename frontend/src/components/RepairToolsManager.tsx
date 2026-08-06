import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Mail,
  Network,
  RefreshCw,
  Server,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageChrome";

interface RepairScript {
  id: string;
  title: string;
  description: string;
  category: string;
  risk: string;
  script: string;
  available: boolean;
}

interface Overview {
  src_dir: string;
  src_exists: boolean;
  agent_installed: boolean;
  busy: boolean;
  scripts: RepairScript[];
  recent_jobs: Array<{
    job_id: string;
    ok: boolean | null;
    pending?: boolean;
    error?: string;
    step?: string;
    script_id?: string;
    script?: string;
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
  script_id: string;
  script: string;
  step: string;
  log: string;
  finished_at?: string;
  started_at?: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  mail: "Messagerie",
  panel: "Panel",
  web: "Sites web",
  network: "Réseau",
};

const CATEGORY_ORDER = ["mail", "panel", "web", "network"];

async function waitForApi(timeoutMs = 120_000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch("/api/v1/health/", { cache: "no-store" });
      if (res.ok) return true;
    } catch {
      /* API may restart */
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  return false;
}

export function RepairToolsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [activeScript, setActiveScript] = useState<string | null>(null);
  const [apiDown, setApiDown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLPreElement>(null);
  const activeRef = useRef(false);

  const { data: overview, isLoading } = useQuery({
    queryKey: ["repairs-overview"],
    queryFn: () => apiRequest<Overview>("/server-setup/repairs/"),
    refetchInterval: jobId && job?.pending ? false : 15_000,
  });

  const start = useMutation({
    mutationFn: (scriptId: string) =>
      apiRequest<{ job_id: string; message: string; script_id: string }>(
        "/server-setup/repairs/start/",
        {
          method: "POST",
          body: JSON.stringify({ script_id: scriptId }),
        },
      ),
    onSuccess: (data) => {
      setError(null);
      setActiveScript(data.script_id);
      setJobId(data.job_id);
      setJob({
        job_id: data.job_id,
        state: "running",
        pending: true,
        ok: null,
        error: "",
        script_id: data.script_id,
        script: "",
        step: "queued",
        log: "",
      });
      void qc.invalidateQueries({ queryKey: ["repairs-overview"] });
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
          const data = await apiRequest<JobStatus>(`/server-setup/repairs/jobs/${jobId}/`);
          if (cancelled) return;
          setApiDown(false);
          setJob(data);
          if (!data.pending) {
            activeRef.current = false;
            void qc.invalidateQueries({ queryKey: ["repairs-overview"] });
            return;
          }
        } catch {
          if (cancelled) return;
          setApiDown(true);
          const up = await waitForApi(12_000);
          if (cancelled) return;
          if (up) setApiDown(false);
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

  const byCategory = useMemo(() => {
    const scripts = overview?.scripts || [];
    const map = new Map<string, RepairScript[]>();
    for (const s of scripts) {
      const list = map.get(s.category) || [];
      list.push(s);
      map.set(s.category, list);
    }
    return CATEGORY_ORDER.filter((c) => map.has(c)).map((c) => ({
      id: c,
      label: CATEGORY_LABELS[c] || c,
      items: map.get(c) || [],
    }));
  }, [overview?.scripts]);

  const busy = Boolean(overview?.busy || (job?.pending && jobId) || start.isPending);
  const catIcon = (id: string) => {
    if (id === "mail") return Mail;
    if (id === "network") return Network;
    if (id === "panel") return Server;
    return Wrench;
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={title}
        subtitle="Scripts de réparation d’urgence (hors installation initiale). Lancement root sécurisé via allowlist."
      />

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-[var(--vz-muted)]">
          <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
        </div>
      )}

      {overview && !overview.agent_installed && (
        <div className="flex gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div>
            <p className="font-medium">Agent de réparation non installé</p>
            <p className="mt-1 text-[var(--vz-muted)]">
              Une fois en SSH :{" "}
              <code className="text-xs">sudo bash /opt/vzone-src/scripts/install-repair-agent.sh</code>
              {" "}(aussi installé par Panel Update / update.sh).
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {byCategory.map((cat) => {
        const Icon = catIcon(cat.id);
        return (
          <section key={cat.id} className="space-y-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-[var(--vz-muted)]">
              <Icon className="h-4 w-4" />
              {cat.label}
            </h2>
            <div className="grid gap-3 md:grid-cols-2">
              {cat.items.map((script) => {
                const runningThis =
                  busy && (activeScript === script.id || job?.script_id === script.id) && job?.pending;
                return (
                  <div
                    key={script.id}
                    className="flex flex-col gap-3 rounded-xl border border-[var(--vz-border)] bg-[var(--vz-surface)] p-4"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="font-medium leading-snug">{script.title}</h3>
                        <p className="mt-1 text-xs text-[var(--vz-muted)]">{script.description}</p>
                        <p className="mt-2 font-mono text-[10px] text-[var(--vz-muted)]">{script.script}</p>
                      </div>
                      {script.risk === "caution" && (
                        <span title="À utiliser avec précaution">
                          <ShieldAlert className="h-4 w-4 shrink-0 text-amber-600" />
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      disabled={
                        busy ||
                        !overview?.agent_installed ||
                        !script.available ||
                        !overview.src_exists
                      }
                      onClick={() => {
                        if (
                          script.risk === "caution" &&
                          !window.confirm(`Lancer « ${script.title} » ?`)
                        ) {
                          return;
                        }
                        start.mutate(script.id);
                      }}
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--vz-accent)] px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {runningThis ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" /> En cours…
                        </>
                      ) : (
                        <>
                          <Wrench className="h-4 w-4" /> Lancer
                        </>
                      )}
                    </button>
                    {!script.available && (
                      <p className="text-xs text-amber-700 dark:text-amber-400">Script absent sur le serveur</p>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}

      {(job || apiDown) && (
        <section className="space-y-2 rounded-xl border border-[var(--vz-border)] bg-[var(--vz-surface)] p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Journal</h2>
            <div className="flex items-center gap-2 text-xs text-[var(--vz-muted)]">
              {apiDown && <span className="text-amber-600">API temporairement indisponible…</span>}
              {job?.pending && (
                <span className="inline-flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" /> {job.step}
                </span>
              )}
              {job && !job.pending && job.ok && (
                <span className="inline-flex items-center gap-1 text-emerald-600">
                  <CheckCircle2 className="h-3.5 w-3.5" /> OK
                </span>
              )}
              {job && !job.pending && job.ok === false && (
                <span className="inline-flex items-center gap-1 text-red-600">
                  <AlertTriangle className="h-3.5 w-3.5" /> {job.error || "Échec"}
                </span>
              )}
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded border border-[var(--vz-border)] px-2 py-1"
                onClick={() => void qc.invalidateQueries({ queryKey: ["repairs-overview"] })}
              >
                <RefreshCw className="h-3 w-3" /> Rafraîchir
              </button>
            </div>
          </div>
          <pre
            ref={logRef}
            className="max-h-80 overflow-auto rounded-lg bg-black/90 p-3 font-mono text-[11px] leading-relaxed text-emerald-300"
          >
            {job?.log || "En attente de sortie…"}
          </pre>
        </section>
      )}

      {overview && overview.recent_jobs.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--vz-muted)]">Récent</h2>
          <ul className="space-y-1 text-sm">
            {overview.recent_jobs.map((j) => (
              <li
                key={j.job_id}
                className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--vz-border)] px-3 py-2"
              >
                <span className="font-mono text-xs">{j.script_id || j.script || j.job_id}</span>
                {j.pending ? (
                  <span className="text-amber-600">en cours</span>
                ) : j.ok ? (
                  <span className="text-emerald-600">OK</span>
                ) : (
                  <span className="text-red-600">{j.error || "échec"}</span>
                )}
                <span className="text-xs text-[var(--vz-muted)]">
                  {j.finished_at || j.started_at || ""}
                </span>
                <button
                  type="button"
                  className="ml-auto text-xs text-[var(--vz-accent)] underline"
                  onClick={() => {
                    setJobId(j.job_id);
                    setActiveScript(j.script_id || null);
                  }}
                >
                  Voir log
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
