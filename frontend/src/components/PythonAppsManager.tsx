import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Copy,
  FileText,
  FolderOpen,
  Globe2,
  Loader2,
  Package,
  Play,
  Plus,
  RefreshCw,
  Square,
  Terminal,
  Trash2,
  Download,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";

interface PyOverview {
  apps: number;
  running: number;
  stopped: number;
  error: number;
  provision_mode: string;
  home_path?: string;
}

interface PythonApp {
  id: number;
  name: string;
  label: string;
  python_version: string;
  mode: string;
  framework: string;
  relative_root: string;
  absolute_root: string;
  home_path: string;
  entrypoint: string;
  passenger_wsgi: string;
  port: number;
  status: string;
  domain_name: string;
  last_error: string;
  venv_path: string;
  enter_command: string;
  deploy_command: string;
  django_project: string;
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    return true;
  }
}

function statusMeta(status: string) {
  if (status === "running") {
    return {
      label: "En cours",
      dot: "bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.2)]",
      badge: "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:ring-emerald-800",
    };
  }
  if (status === "error") {
    return {
      label: "Erreur",
      dot: "bg-red-500 shadow-[0_0_0_3px_rgba(239,68,68,0.2)]",
      badge: "bg-red-50 text-red-800 ring-red-200 dark:bg-red-950/40 dark:text-red-300 dark:ring-red-900",
    };
  }
  return {
    label: "Arrêtée",
    dot: "bg-slate-400",
    badge: "bg-slate-100 text-slate-700 ring-slate-200 dark:bg-ink-900 dark:text-ink-200 dark:ring-ink-700",
  };
}

function frameworkLabel(fw: string) {
  const map: Record<string, string> = {
    django: "Django",
    flask: "Flask",
    fastapi: "FastAPI",
    generic: "Python",
  };
  return map[fw] || fw;
}

function DeployPanel({
  app,
  onClose,
}: {
  app: PythonApp;
  onClose?: () => void;
}) {
  const [copied, setCopied] = useState<"enter" | "deploy" | "root" | null>(null);

  async function copy(kind: "enter" | "deploy" | "root") {
    const text =
      kind === "enter"
        ? app.enter_command
        : kind === "deploy"
          ? app.deploy_command
          : app.absolute_root || app.relative_root;
    if (!text) return;
    await copyText(text);
    setCopied(kind);
    window.setTimeout(() => setCopied(null), 2000);
  }

  return (
    <div className="mt-4 space-y-3 rounded-lg border border-cp-navy/15 bg-gradient-to-b from-cp-canvas to-white p-4 dark:from-ink-900 dark:to-ink-950 dark:border-ink-700">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-cp-navy dark:text-ink-50">
            <Terminal className="h-4 w-4 text-cp-orange" />
            Déploiement SSH — {app.name}
          </h3>
          <p className="mt-1 text-xs text-cp-muted">
            Collez la commande dans un terminal SSH (comme cPanel), puis Start pour publier.
          </p>
        </div>
        {onClose && (
          <button type="button" className="vz-btn-ghost !px-2.5 !py-1 text-xs" onClick={onClose}>
            Fermer
          </button>
        )}
      </div>

      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">
            Application root (projet)
          </p>
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-cp-link hover:underline"
            onClick={() => void copy("root")}
          >
            {copied === "root" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied === "root" ? "Copié" : "Copier"}
          </button>
        </div>
        <code className="block break-all rounded-md border border-cp-border/80 bg-white px-3 py-2 font-mono text-xs dark:border-ink-700 dark:bg-ink-950">
          {app.absolute_root || app.relative_root}
        </code>
        {app.passenger_wsgi && (
          <p className="text-[11px] text-cp-muted">
            <span className="font-medium text-cp-text">passenger_wsgi.py</span> :{" "}
            <code className="font-mono">{app.passenger_wsgi}</code>
          </p>
        )}
        {app.venv_path && (
          <p className="text-[11px] text-cp-muted">
            <span className="font-medium text-cp-text">virtualenv</span> :{" "}
            <code className="font-mono">{app.venv_path}</code>
          </p>
        )}
      </div>

      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">
            Commande à coller
          </p>
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-cp-link hover:underline"
            onClick={() => void copy("enter")}
          >
            {copied === "enter" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied === "enter" ? "Copié" : "Copier"}
          </button>
        </div>
        <pre className="overflow-x-auto rounded-md bg-[#0f172a] px-3 py-2.5 font-mono text-xs leading-relaxed text-emerald-300">
          {app.enter_command || "(indisponible)"}
        </pre>
      </div>

      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">
            Script {frameworkLabel(app.framework)}
          </p>
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-cp-link hover:underline"
            onClick={() => void copy("deploy")}
          >
            {copied === "deploy" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied === "deploy" ? "Copié" : "Copier tout"}
          </button>
        </div>
        <pre className="max-h-56 overflow-auto rounded-md bg-[#0f172a] px-3 py-2.5 font-mono text-xs leading-relaxed text-slate-200 whitespace-pre-wrap">
          {app.deploy_command || "(indisponible)"}
        </pre>
      </div>

      {app.framework === "django" && (
        <p className="rounded-md border border-cp-border/70 bg-white/80 px-3 py-2 text-xs text-cp-muted dark:bg-ink-950/60">
          Projet attendu :{" "}
          <code className="font-mono text-cp-text">{app.django_project || "config"}</code> —{" "}
          <code className="font-mono text-cp-text">
            DJANGO_SETTINGS_MODULE={app.django_project || "config"}.settings
          </code>
        </p>
      )}
    </div>
  );
}

function AppCard({
  app,
  expanded,
  busy,
  onToggleDeploy,
  onAction,
  onLogs,
  onRemove,
}: {
  app: PythonApp;
  expanded: boolean;
  busy: boolean;
  onToggleDeploy: () => void;
  onAction: (op: string) => void;
  onLogs: () => void;
  onRemove: () => void;
}) {
  const st = statusMeta(app.status);
  const running = app.status === "running";

  return (
    <article
      className={`vz-panel overflow-hidden transition ${
        expanded ? "ring-2 ring-cp-link/25 border-cp-link/40" : ""
      }`}
    >
      <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${st.dot}`} />
            <h3 className="truncate font-semibold text-cp-navy dark:text-ink-50">{app.label || app.name}</h3>
            <span className="rounded-md bg-cp-navy/5 px-2 py-0.5 font-mono text-[11px] text-cp-muted dark:bg-ink-900">
              {app.name}
            </span>
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${st.badge}`}
            >
              {st.label}
            </span>
          </div>

          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-1 rounded-md border border-cp-border/80 bg-cp-canvas/80 px-2 py-1 text-[11px] font-medium text-cp-text dark:border-ink-700 dark:bg-ink-900">
              <Package className="h-3 w-3 text-cp-orange" />
              {frameworkLabel(app.framework)}
            </span>
            <span className="inline-flex items-center rounded-md border border-cp-border/80 bg-cp-canvas/80 px-2 py-1 text-[11px] text-cp-muted dark:border-ink-700 dark:bg-ink-900">
              {app.mode.toUpperCase()} · Python {app.python_version}
            </span>
            <span className="inline-flex items-center rounded-md border border-cp-border/80 bg-cp-canvas/80 px-2 py-1 font-mono text-[11px] text-cp-muted dark:border-ink-700 dark:bg-ink-900">
              :{app.port}
            </span>
            {app.domain_name && (
              <span className="inline-flex items-center gap-1 rounded-md border border-cp-border/80 bg-cp-canvas/80 px-2 py-1 text-[11px] text-cp-text dark:border-ink-700 dark:bg-ink-900">
                <Globe2 className="h-3 w-3 text-cp-link" />
                {app.domain_name}
              </span>
            )}
          </div>

          <div className="flex items-start gap-2 text-xs text-cp-muted">
            <FolderOpen className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cp-orange" />
            <div className="min-w-0">
              <p className="font-mono text-cp-text dark:text-ink-200">{app.relative_root}</p>
              {app.absolute_root && (
                <p className="mt-0.5 truncate font-mono text-[11px] opacity-80" title={app.absolute_root}>
                  {app.absolute_root}
                </p>
              )}
            </div>
          </div>

          {app.last_error && app.status === "error" && (
            <p className="rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs text-cp-danger dark:border-red-900 dark:bg-red-950/30">
              {app.last_error}
            </p>
          )}
        </div>

        <div className="flex shrink-0 flex-wrap gap-1.5 sm:max-w-[280px] sm:justify-end">
          <button
            type="button"
            className={`vz-btn-ghost !px-2.5 !py-1.5 text-xs ${expanded ? "!border-cp-link !bg-cp-link-soft" : ""}`}
            onClick={onToggleDeploy}
            title="Commande SSH"
          >
            <Terminal className="h-3.5 w-3.5" />
            SSH
          </button>
          {!running ? (
            <button
              type="button"
              className="vz-btn-primary !px-2.5 !py-1.5 text-xs"
              disabled={busy}
              onClick={() => onAction("start")}
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              Start
            </button>
          ) : (
            <button
              type="button"
              className="vz-btn-ghost !px-2.5 !py-1.5 text-xs"
              disabled={busy}
              onClick={() => onAction("stop")}
            >
              <Square className="h-3.5 w-3.5" />
              Stop
            </button>
          )}
          <button
            type="button"
            className="vz-btn-ghost !px-2.5 !py-1.5 text-xs"
            disabled={busy}
            onClick={() => onAction("restart")}
            title="Restart"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="vz-btn-ghost !px-2.5 !py-1.5 text-xs"
            disabled={busy}
            onClick={() => onAction("install")}
            title="pip install -r requirements.txt"
          >
            <Download className="h-3.5 w-3.5" />
            pip
          </button>
          <button
            type="button"
            className="vz-btn-ghost !px-2.5 !py-1.5 text-xs"
            onClick={onLogs}
            title="Logs"
          >
            <FileText className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="vz-btn-ghost !px-2.5 !py-1.5 text-xs text-cp-danger hover:!border-red-300 hover:!bg-red-50 dark:hover:!bg-red-950/30"
            onClick={onRemove}
            title="Supprimer"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-cp-border/80 px-4 pb-4 dark:border-ink-800">
          <DeployPanel app={app} onClose={onToggleDeploy} />
        </div>
      )}
    </article>
  );
}

export function PythonAppsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["python-overview"],
    queryFn: () => apiRequest<PyOverview>("/python/overview/"),
  });
  const { data: apps = [], isLoading } = useQuery({
    queryKey: ["python-apps"],
    queryFn: () => apiRequest<PythonApp[]>("/python/apps/"),
  });

  const [form, setForm] = useState({
    name: "",
    mode: "wsgi",
    framework: "django",
    python_version: "3.12",
    domain_name: "",
    relative_root: "",
  });
  const [logs, setLogs] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createdApp, setCreatedApp] = useState<PythonApp | null>(null);
  const [focusId, setFocusId] = useState<number | null>(null);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["python-overview"] });
    void qc.invalidateQueries({ queryKey: ["python-apps"] });
  };

  const create = useMutation({
    mutationFn: () =>
      runWithProgress(
        `Création app Python · ${form.name || "app"}`,
        () =>
          apiRequest<PythonApp>("/python/apps/", {
            method: "POST",
            body: JSON.stringify({
              name: form.name,
              mode: form.mode,
              framework: form.framework,
              python_version: form.python_version,
              domain_name: form.domain_name,
              relative_root: form.relative_root.trim() || form.name.trim(),
            }),
          }),
        {
          tickDetail: (ms) =>
            ms < 2500 ? "Création application root + passenger_wsgi…" : "Préparation virtualenv…",
        },
      ),
    onSuccess: (app) => {
      setCreatedApp(app);
      setFocusId(app.id);
      setForm({
        name: "",
        mode: "wsgi",
        framework: "django",
        python_version: "3.12",
        domain_name: "",
        relative_root: "",
      });
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const action = useMutation({
    mutationFn: ({ id, op, name }: { id: number; op: string; name: string }) =>
      runWithProgress(`Python ${op} · ${name}`, () =>
        apiRequest(`/python/apps/${id}/${op}/`, { method: "POST", body: "{}" }),
      ),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/python/apps/${id}/?remove_files=false`, { method: "DELETE" }),
    onSuccess: (_d, id) => {
      if (createdApp?.id === id) setCreatedApp(null);
      if (focusId === id) setFocusId(null);
      invalidate();
    },
  });

  const loadLogs = useMutation({
    mutationFn: (id: number) => apiRequest<Record<string, string>>(`/python/apps/${id}/logs/`),
    onSuccess: (data) => setLogs(data),
    onError: (err: Error) => setError(err.message),
  });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  const focusedId =
    focusId ?? (createdApp && apps.some((a) => a.id === createdApp.id) ? createdApp.id : null);

  return (
    <div className="space-y-5 animate-fade-up">
      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border/80 bg-gradient-to-r from-cp-navy/[0.04] to-transparent px-5 py-4 dark:border-ink-800 dark:from-ink-900">
          <h1 className="text-xl font-semibold text-cp-navy dark:text-ink-50">{title}</h1>
          <p className="mt-1 max-w-2xl text-sm text-cp-muted">
            Comme cPanel Setup Python App : indiquez l&apos;Application root (dossier du projet
            Django). <code className="font-mono text-xs">passenger_wsgi.py</code> est créé dans ce
            même dossier que <code className="font-mono text-xs">manage.py</code> ; le venv est sous{" "}
            <code className="font-mono text-xs">virtualenv/</code>.
          </p>
        </div>

        <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Applications", value: overview?.apps ?? "—", tone: "text-cp-navy dark:text-ink-50" },
            { label: "En cours", value: overview?.running ?? "—", tone: "text-emerald-700 dark:text-emerald-400" },
            { label: "Arrêtées", value: overview?.stopped ?? "—", tone: "text-cp-muted" },
            { label: "Erreurs", value: overview?.error ?? "—", tone: "text-cp-danger" },
          ].map((card) => (
            <div
              key={card.label}
              className="rounded-lg border border-cp-border/70 bg-cp-canvas/50 px-4 py-3 dark:border-ink-800 dark:bg-ink-900/40"
            >
              <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">{card.label}</p>
              <p className={`mt-1 text-2xl font-semibold tabular-nums ${card.tone}`}>{card.value}</p>
            </div>
          ))}
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger dark:border-red-900 dark:bg-red-950/30">
          {error}
        </p>
      )}

      <form className="vz-panel p-4 sm:p-5" onSubmit={onCreate}>
        <div className="mb-3 flex items-center gap-2">
          <Plus className="h-4 w-4 text-cp-orange" />
          <h2 className="text-sm font-semibold text-cp-navy dark:text-ink-50">
            CREATE APPLICATION
          </h2>
        </div>
        <p className="mb-4 text-xs text-cp-muted">
          Home :{" "}
          <code className="font-mono">{overview?.home_path || "~/"}</code>
          {" — "}
          l&apos;Application root est relatif à ce home (ex.{" "}
          <code className="font-mono">mydjango</code>).
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="space-y-1">
            <span className="text-[11px] font-medium text-cp-muted">Application name *</span>
            <input
              className="vz-input"
              placeholder="ex: webapp"
              required
              value={form.name}
              onChange={(e) => {
                const name = e.target.value;
                setForm((prev) => ({
                  ...prev,
                  name,
                  // Comme cPanel : préremplir l'application root avec le nom si encore vide / synchro
                  relative_root:
                    !prev.relative_root || prev.relative_root === prev.name ? name : prev.relative_root,
                }));
              }}
            />
          </label>
          <label className="space-y-1 sm:col-span-2">
            <span className="text-[11px] font-medium text-cp-muted">
              Application root * (chemin du projet Django)
            </span>
            <div className="flex overflow-hidden rounded-lg border border-cp-border focus-within:border-cp-link focus-within:ring-2 focus-within:ring-cp-link/20 dark:border-ink-700">
              <span className="flex max-w-[45%] items-center truncate border-r border-cp-border bg-cp-canvas/80 px-2 font-mono text-[11px] text-cp-muted dark:border-ink-700 dark:bg-ink-900">
                {(overview?.home_path || "~").replace(/\/$/, "")}/
              </span>
              <input
                className="vz-input !rounded-none !border-0 !ring-0"
                placeholder="mydjango"
                required={form.framework === "django"}
                value={form.relative_root}
                onChange={(e) => setForm({ ...form, relative_root: e.target.value.replace(/^\/+/, "") })}
              />
            </div>
            <span className="text-[11px] text-cp-muted">
              Ici seront créés <code className="font-mono">passenger_wsgi.py</code> + votre projet (
              <code className="font-mono">manage.py</code>). Pas de sous-dossier <code className="font-mono">apps/</code>.
            </span>
          </label>
          <label className="space-y-1">
            <span className="text-[11px] font-medium text-cp-muted">Application URL / domaine</span>
            <input
              className="vz-input"
              placeholder="app.exemple.com (opt.)"
              value={form.domain_name}
              onChange={(e) => setForm({ ...form, domain_name: e.target.value })}
            />
          </label>
          <label className="space-y-1">
            <span className="text-[11px] font-medium text-cp-muted">Python version</span>
            <input
              className="vz-input"
              placeholder="3.12"
              value={form.python_version}
              onChange={(e) => setForm({ ...form, python_version: e.target.value })}
            />
          </label>
          <label className="space-y-1">
            <span className="text-[11px] font-medium text-cp-muted">Framework</span>
            <select
              className="vz-input"
              value={form.framework}
              onChange={(e) => {
                const framework = e.target.value;
                setForm({
                  ...form,
                  framework,
                  mode: framework === "django" ? "wsgi" : framework === "fastapi" ? "asgi" : form.mode,
                });
              }}
            >
              <option value="django">Django</option>
              <option value="generic">Generic</option>
              <option value="flask">Flask</option>
              <option value="fastapi">FastAPI</option>
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-[11px] font-medium text-cp-muted">Application startup file</span>
            <input
              className="vz-input"
              readOnly
              value={form.framework === "fastapi" || form.mode === "asgi" ? "asgi.py" : "passenger_wsgi.py"}
            />
          </label>
          <div className="flex items-end sm:col-span-2 lg:col-span-1">
            <button className="vz-btn-primary w-full" type="submit" disabled={create.isPending}>
              {create.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              CREATE
            </button>
          </div>
        </div>
      </form>

      <section className="space-y-3">
        <div className="flex items-end justify-between gap-3 px-0.5">
          <div>
            <h2 className="text-sm font-semibold text-cp-navy dark:text-ink-50">Applications</h2>
            <p className="text-xs text-cp-muted">
              {apps.length} application{apps.length === 1 ? "" : "s"} · cliquez SSH pour la commande
              terminal
            </p>
          </div>
        </div>

        {isLoading && (
          <div className="vz-panel flex items-center gap-2 px-4 py-8 text-sm text-cp-muted">
            <Loader2 className="h-4 w-4 animate-spin text-cp-orange" />
            Chargement des applications…
          </div>
        )}

        {!isLoading && apps.length === 0 && (
          <div className="vz-panel flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-cp-navy/5 text-cp-orange dark:bg-ink-900">
              <Package className="h-6 w-6" />
            </div>
            <p className="text-sm font-medium text-cp-navy dark:text-ink-50">Aucune application</p>
            <p className="max-w-sm text-xs text-cp-muted">
              Créez une app Django ci-dessus : le panel générera le venv et la commande à coller en
              SSH.
            </p>
          </div>
        )}

        <div className="space-y-3">
          {apps.map((app) => (
            <AppCard
              key={app.id}
              app={app}
              expanded={focusedId === app.id}
              busy={action.isPending}
              onToggleDeploy={() => {
                if (focusedId === app.id) {
                  setFocusId(null);
                  setCreatedApp(null);
                } else {
                  setFocusId(app.id);
                  setCreatedApp(app);
                }
              }}
              onAction={(op) => action.mutate({ id: app.id, op, name: app.name })}
              onLogs={() => loadLogs.mutate(app.id)}
              onRemove={() => {
                if (window.confirm(`Supprimer ${app.name} ?`)) remove.mutate(app.id);
              }}
            />
          ))}
        </div>
      </section>

      {logs && (
        <div className="vz-panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-cp-navy dark:text-ink-50">
              <FileText className="h-4 w-4 text-cp-orange" />
              Logs
            </h2>
            <button type="button" className="vz-btn-ghost !px-2.5 !py-1 text-xs" onClick={() => setLogs(null)}>
              Fermer
            </button>
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            {Object.entries(logs).map(([name, content]) => (
              <div key={name} className="min-w-0">
                <p className="mb-1 font-mono text-[11px] font-semibold text-cp-orange">{name}</p>
                <pre className="max-h-48 overflow-auto rounded-lg border border-cp-border/70 bg-cp-canvas p-3 text-xs dark:border-ink-800 dark:bg-ink-900">
                  {content || "(vide)"}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
