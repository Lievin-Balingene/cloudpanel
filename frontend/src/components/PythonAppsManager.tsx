import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Terminal } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";

interface PyOverview {
  apps: number;
  running: number;
  stopped: number;
  error: number;
  provision_mode: string;
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
  entrypoint: string;
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

function DeployPanel({
  app,
  onClose,
}: {
  app: PythonApp;
  onClose?: () => void;
}) {
  const [copied, setCopied] = useState<"enter" | "deploy" | null>(null);

  async function copy(kind: "enter" | "deploy") {
    const text = kind === "enter" ? app.enter_command : app.deploy_command;
    if (!text) return;
    await copyText(text);
    setCopied(kind);
    window.setTimeout(() => setCopied(null), 2000);
  }

  return (
    <div className="vz-panel space-y-3 border border-cp-orange/30 bg-cp-canvas/40 p-4 dark:bg-ink-900/40">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Terminal className="h-4 w-4 text-cp-orange" />
            Déployer {app.name} (SSH)
          </h2>
          <p className="mt-1 text-xs text-cp-muted">
            Comme sur cPanel : collez la commande dans un terminal SSH, puis déployez votre code
            Django / Python dans ce dossier.
          </p>
        </div>
        {onClose && (
          <button type="button" className="text-sm text-cp-link hover:underline" onClick={onClose}>
            Fermer
          </button>
        )}
      </div>

      <div className="space-y-1">
        <p className="text-xs font-medium text-cp-muted">Application root</p>
        <code className="block break-all rounded bg-white px-3 py-2 font-mono text-xs dark:bg-ink-950">
          {app.absolute_root || app.relative_root}
        </code>
      </div>

      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-medium text-cp-muted">
            Commande à coller (activer le venv + entrer dans l’app)
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
        <pre className="overflow-x-auto rounded bg-ink-950 px-3 py-2 font-mono text-xs text-emerald-300">
          {app.enter_command || "(indisponible)"}
        </pre>
      </div>

      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-medium text-cp-muted">
            Script de déploiement {app.framework === "django" ? "Django" : app.framework}
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
        <pre className="max-h-64 overflow-auto rounded bg-ink-950 px-3 py-2 font-mono text-xs text-slate-200 whitespace-pre-wrap">
          {app.deploy_command || "(indisponible)"}
        </pre>
      </div>

      {app.framework === "django" && (
        <p className="text-xs text-cp-muted">
          Projet attendu : <code className="font-mono">{app.django_project || "config"}</code> (
          <code className="font-mono">DJANGO_SETTINGS_MODULE={app.django_project || "config"}.settings</code>
          ). Après le script, cliquez <strong>Start</strong> dans le panel.
        </p>
      )}
    </div>
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
            body: JSON.stringify(form),
          }),
        {
          tickDetail: (ms) =>
            ms < 2500 ? "Provisionnement venv…" : "Génération de la commande de déploiement…",
        },
      ),
    onSuccess: (app) => {
      setCreatedApp(app);
      setFocusId(app.id);
      setForm({ name: "", mode: "wsgi", framework: "django", python_version: "3.12", domain_name: "" });
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
    onSuccess: invalidate,
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

  const focused =
    (focusId != null ? apps.find((a) => a.id === focusId) : null) ||
    (createdApp && (!apps.length || apps.some((a) => a.id === createdApp.id)) ? createdApp : null);

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-cp-muted">
          Créez une app Django / Python : le panel génère un chemin et une commande à coller dans
          le terminal SSH (style cPanel), puis Start pour publier.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Apps", value: overview?.apps ?? "—" },
          { label: "Running", value: overview?.running ?? "—" },
          { label: "Stopped", value: overview?.stopped ?? "—" },
          { label: "Erreur", value: overview?.error ?? "—" },
        ].map((card) => (
          <div key={card.label} className="vz-panel p-4">
            <p className="text-xs font-semibold uppercase text-cp-muted">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold text-cp-orange">{card.value}</p>
          </div>
        ))}
      </div>

      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">{error}</p>
      )}

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-6" onSubmit={onCreate}>
        <input
          className="vz-input"
          placeholder="nom (ex: webapp)"
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <select
          className="vz-input"
          value={form.mode}
          onChange={(e) => setForm({ ...form, mode: e.target.value })}
          disabled={form.framework === "django"}
        >
          <option value="wsgi">WSGI</option>
          <option value="asgi">ASGI</option>
        </select>
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
        <input
          className="vz-input"
          placeholder="python"
          value={form.python_version}
          onChange={(e) => setForm({ ...form, python_version: e.target.value })}
        />
        <input
          className="vz-input"
          placeholder="domaine (opt.)"
          value={form.domain_name}
          onChange={(e) => setForm({ ...form, domain_name: e.target.value })}
        />
        <button className="vz-btn-primary" type="submit" disabled={create.isPending}>
          Créer app
        </button>
      </form>

      {focused && (
        <DeployPanel
          app={focused}
          onClose={() => {
            setFocusId(null);
            setCreatedApp(null);
          }}
        />
      )}

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">App</th>
              <th className="px-3 py-2">Mode</th>
              <th className="px-3 py-2">Chemin</th>
              <th className="px-3 py-2">Port</th>
              <th className="px-3 py-2">État</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={6}>
                  Chargement…
                </td>
              </tr>
            )}
            {apps.map((app) => (
              <tr key={app.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2">
                  <div className="font-mono text-xs">{app.name}</div>
                  <div className="text-xs text-cp-muted">
                    {app.framework} · py{app.python_version}
                  </div>
                </td>
                <td className="px-3 py-2">{app.mode}</td>
                <td className="px-3 py-2 font-mono text-xs">
                  <div>{app.relative_root}</div>
                  {app.absolute_root && (
                    <div className="mt-0.5 max-w-[220px] truncate text-[10px] text-cp-muted" title={app.absolute_root}>
                      {app.absolute_root}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2">{app.port}</td>
                <td className="px-3 py-2">
                  <span
                    className={
                      app.status === "running"
                        ? "text-cp-success"
                        : app.status === "error"
                          ? "text-cp-danger"
                          : "text-cp-muted"
                    }
                  >
                    {app.status}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="font-medium text-cp-orange hover:underline"
                      onClick={() => {
                        setFocusId(app.id);
                        setCreatedApp(app);
                      }}
                    >
                      Commande SSH
                    </button>
                    {app.status !== "running" ? (
                      <button
                        type="button"
                        className="text-cp-link hover:underline"
                        onClick={() => action.mutate({ id: app.id, op: "start", name: app.name })}
                      >
                        Start
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="text-cp-link hover:underline"
                        onClick={() => action.mutate({ id: app.id, op: "stop", name: app.name })}
                      >
                        Stop
                      </button>
                    )}
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => action.mutate({ id: app.id, op: "restart", name: app.name })}
                    >
                      Restart
                    </button>
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => action.mutate({ id: app.id, op: "install", name: app.name })}
                    >
                      pip install
                    </button>
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => loadLogs.mutate(app.id)}
                    >
                      Logs
                    </button>
                    <button
                      type="button"
                      className="text-cp-danger hover:underline"
                      onClick={() => {
                        if (window.confirm(`Supprimer ${app.name} ?`)) remove.mutate(app.id);
                      }}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && apps.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={6}>
                  Aucune application Python.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {logs && (
        <div className="vz-panel p-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase text-cp-muted">Logs</h2>
            <button type="button" className="text-cp-link text-sm hover:underline" onClick={() => setLogs(null)}>
              Fermer
            </button>
          </div>
          {Object.entries(logs).map(([name, content]) => (
            <div key={name} className="mb-3">
              <p className="mb-1 font-mono text-xs text-cp-orange">{name}</p>
              <pre className="max-h-48 overflow-auto rounded bg-cp-canvas p-3 text-xs dark:bg-ink-900">
                {content || "(vide)"}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
