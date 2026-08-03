import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

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
  entrypoint: string;
  port: number;
  status: string;
  domain_name: string;
  last_error: string;
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
    framework: "generic",
    python_version: "3.12",
    domain_name: "",
  });
  const [logs, setLogs] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["python-overview"] });
    void qc.invalidateQueries({ queryKey: ["python-apps"] });
  };

  const create = useMutation({
    mutationFn: () =>
      apiRequest("/python/apps/", { method: "POST", body: JSON.stringify(form) }),
    onSuccess: () => {
      setForm({ name: "", mode: "wsgi", framework: "generic", python_version: "3.12", domain_name: "" });
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const action = useMutation({
    mutationFn: ({ id, op }: { id: number; op: string }) =>
      apiRequest(`/python/apps/${id}/${op}/`, { method: "POST", body: "{}" }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/python/apps/${id}/?remove_files=false`, { method: "DELETE" }),
    onSuccess: invalidate,
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

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-cp-muted">
          Applications Python WSGI/ASGI — venv, démarrage, requirements et logs.
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
        >
          <option value="wsgi">WSGI</option>
          <option value="asgi">ASGI</option>
        </select>
        <select
          className="vz-input"
          value={form.framework}
          onChange={(e) => setForm({ ...form, framework: e.target.value })}
        >
          <option value="generic">Generic</option>
          <option value="django">Django</option>
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
                <td className="px-3 py-2 font-mono text-xs">{app.relative_root}</td>
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
                    {app.status !== "running" ? (
                      <button
                        type="button"
                        className="text-cp-link hover:underline"
                        onClick={() => action.mutate({ id: app.id, op: "start" })}
                      >
                        Start
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="text-cp-link hover:underline"
                        onClick={() => action.mutate({ id: app.id, op: "stop" })}
                      >
                        Stop
                      </button>
                    )}
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => action.mutate({ id: app.id, op: "restart" })}
                    >
                      Restart
                    </button>
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => action.mutate({ id: app.id, op: "install" })}
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
