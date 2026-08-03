import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

interface NodeOverview {
  apps: number;
  running: number;
  stopped: number;
  error: number;
  provision_mode: string;
}

interface NodeAppItem {
  id: number;
  name: string;
  label: string;
  node_version: string;
  framework: string;
  relative_root: string;
  start_script: string;
  entrypoint: string;
  port: number;
  status: string;
  domain_name: string;
}

export function NodeAppsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["node-overview"],
    queryFn: () => apiRequest<NodeOverview>("/node/overview/"),
  });
  const { data: apps = [], isLoading } = useQuery({
    queryKey: ["node-apps"],
    queryFn: () => apiRequest<NodeAppItem[]>("/node/apps/"),
  });

  const [form, setForm] = useState({
    name: "",
    framework: "generic",
    node_version: "20",
    domain_name: "",
  });
  const [logs, setLogs] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["node-overview"] });
    void qc.invalidateQueries({ queryKey: ["node-apps"] });
  };

  const create = useMutation({
    mutationFn: () =>
      apiRequest("/node/apps/", { method: "POST", body: JSON.stringify(form) }),
    onSuccess: () => {
      setForm({ name: "", framework: "generic", node_version: "20", domain_name: "" });
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const action = useMutation({
    mutationFn: ({ id, op }: { id: number; op: string }) =>
      apiRequest(`/node/apps/${id}/${op}/`, { method: "POST", body: "{}" }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/node/apps/${id}/?remove_files=false`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const loadLogs = useMutation({
    mutationFn: (id: number) => apiRequest<Record<string, string>>(`/node/apps/${id}/logs/`),
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
          Applications Node.js — package.json, npm install, démarrage et logs.
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

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-5" onSubmit={onCreate}>
        <input
          className="vz-input"
          placeholder="nom (ex: api)"
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <select
          className="vz-input"
          value={form.framework}
          onChange={(e) => setForm({ ...form, framework: e.target.value })}
        >
          <option value="generic">Generic</option>
          <option value="express">Express</option>
          <option value="nest">NestJS</option>
          <option value="next">Next.js</option>
        </select>
        <input
          className="vz-input"
          placeholder="node"
          value={form.node_version}
          onChange={(e) => setForm({ ...form, node_version: e.target.value })}
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
              <th className="px-3 py-2">Chemin</th>
              <th className="px-3 py-2">Port</th>
              <th className="px-3 py-2">État</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={5}>
                  Chargement…
                </td>
              </tr>
            )}
            {apps.map((app) => (
              <tr key={app.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2">
                  <div className="font-mono text-xs">{app.name}</div>
                  <div className="text-xs text-cp-muted">
                    {app.framework} · node{app.node_version}
                  </div>
                </td>
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
                      npm install
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
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Aucune application Node.js.
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
