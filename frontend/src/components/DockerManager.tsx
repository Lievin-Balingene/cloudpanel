import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

interface DockerOverview {
  containers: number;
  running: number;
  stopped: number;
  error: number;
  provision_mode: string;
}

interface DockerContainerItem {
  id: number;
  name: string;
  image: string;
  tag: string;
  image_ref: string;
  status: string;
  ports: Record<string, string>;
  memory_mb: number;
  container_id: string;
  last_error: string;
}

export function DockerManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["docker-overview"],
    queryFn: () => apiRequest<DockerOverview>("/docker/overview/"),
  });
  const { data: containers = [], isLoading } = useQuery({
    queryKey: ["docker-containers"],
    queryFn: () => apiRequest<DockerContainerItem[]>("/docker/containers/"),
  });

  const [form, setForm] = useState({
    name: "",
    image: "nginx",
    tag: "alpine",
    host_port: "8080",
    container_port: "80",
    memory_mb: 512,
  });
  const [logs, setLogs] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["docker-overview"] });
    void qc.invalidateQueries({ queryKey: ["docker-containers"] });
  };

  const create = useMutation({
    mutationFn: () =>
      apiRequest("/docker/containers/", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          image: form.image,
          tag: form.tag,
          memory_mb: form.memory_mb,
          ports: form.host_port ? { [form.host_port]: form.container_port || "80" } : {},
          start_now: true,
        }),
      }),
    onSuccess: () => {
      setForm({ name: "", image: "nginx", tag: "alpine", host_port: "8080", container_port: "80", memory_mb: 512 });
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const action = useMutation({
    mutationFn: ({ id, op }: { id: number; op: string }) =>
      apiRequest(`/docker/containers/${id}/${op}/`, { method: "POST", body: "{}" }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiRequest(`/docker/containers/${id}/`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const loadLogs = useMutation({
    mutationFn: (id: number) =>
      apiRequest<{ logs: string }>(`/docker/containers/${id}/logs/?tail=100`),
    onSuccess: (data) => setLogs(data.logs),
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
          Conteneurs Docker — image, ports, start/stop, logs et quotas.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Conteneurs", value: overview?.containers ?? "—" },
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
          placeholder="nom"
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <input
          className="vz-input"
          placeholder="image"
          required
          value={form.image}
          onChange={(e) => setForm({ ...form, image: e.target.value })}
        />
        <input
          className="vz-input"
          placeholder="tag"
          value={form.tag}
          onChange={(e) => setForm({ ...form, tag: e.target.value })}
        />
        <input
          className="vz-input"
          placeholder="port host"
          value={form.host_port}
          onChange={(e) => setForm({ ...form, host_port: e.target.value })}
        />
        <input
          className="vz-input"
          type="number"
          min={64}
          title="Mémoire Mo"
          value={form.memory_mb}
          onChange={(e) => setForm({ ...form, memory_mb: Number(e.target.value) })}
        />
        <button className="vz-btn-primary" type="submit" disabled={create.isPending}>
          Créer
        </button>
      </form>

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Nom</th>
              <th className="px-3 py-2">Image</th>
              <th className="px-3 py-2">Ports</th>
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
            {containers.map((c) => (
              <tr key={c.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-mono text-xs">{c.name}</td>
                <td className="px-3 py-2 font-mono text-xs">{c.image_ref}</td>
                <td className="px-3 py-2 text-xs">
                  {Object.entries(c.ports || {})
                    .map(([h, ct]) => `${h}→${ct}`)
                    .join(", ") || "—"}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={
                      c.status === "running"
                        ? "text-cp-success"
                        : c.status === "error"
                          ? "text-cp-danger"
                          : "text-cp-muted"
                    }
                  >
                    {c.status}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    {c.status !== "running" ? (
                      <button
                        type="button"
                        className="text-cp-link hover:underline"
                        onClick={() => action.mutate({ id: c.id, op: "start" })}
                      >
                        Start
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="text-cp-link hover:underline"
                        onClick={() => action.mutate({ id: c.id, op: "stop" })}
                      >
                        Stop
                      </button>
                    )}
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => action.mutate({ id: c.id, op: "restart" })}
                    >
                      Restart
                    </button>
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => loadLogs.mutate(c.id)}
                    >
                      Logs
                    </button>
                    <button
                      type="button"
                      className="text-cp-danger hover:underline"
                      onClick={() => {
                        if (window.confirm(`Supprimer ${c.name} ?`)) remove.mutate(c.id);
                      }}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && containers.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Aucun conteneur.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {logs !== null && (
        <div className="vz-panel p-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase text-cp-muted">Logs</h2>
            <button type="button" className="text-cp-link text-sm hover:underline" onClick={() => setLogs(null)}>
              Fermer
            </button>
          </div>
          <pre className="max-h-64 overflow-auto rounded bg-cp-canvas p-3 text-xs dark:bg-ink-900">
            {logs || "(vide)"}
          </pre>
        </div>
      )}
    </div>
  );
}
