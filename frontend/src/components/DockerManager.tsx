import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, FileText, Play, Plus, RefreshCw, Square, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot } from "@/components/ui/PageChrome";

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
  const [createOpen, setCreateOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["docker-overview"] });
    void qc.invalidateQueries({ queryKey: ["docker-containers"] });
  };

  const create = useMutation({
    mutationFn: () =>
      runWithProgress(
        `Docker · ${form.name || form.image}`,
        () =>
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
        {
          detail: `${form.image}:${form.tag}`,
          tickDetail: (ms) =>
            ms < 4000 ? "Pull de l'image…" : "Démarrage du conteneur…",
        },
      ),
    onSuccess: () => {
      setForm({ name: "", image: "nginx", tag: "alpine", host_port: "8080", container_port: "80", memory_mb: 512 });
      setError(null);
      setCreateOpen(false);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const action = useMutation({
    mutationFn: ({ id, op, name }: { id: number; op: string; name: string }) =>
      runWithProgress(`Docker ${op} · ${name}`, () =>
        apiRequest(`/docker/containers/${id}/${op}/`, { method: "POST", body: "{}" }),
      ),
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
      <PageHeader
        title={title}
        subtitle="Conteneurs Docker — images, ports, démarrage, journaux et quotas."
        stats={[
          { label: "Conteneurs", value: overview?.containers ?? "—" },
          { label: "En cours", value: overview?.running ?? "—" },
          { label: "Arrêtés", value: overview?.stopped ?? "—" },
          { label: "Erreurs", value: overview?.error ?? "—" },
        ]}
        actions={<button type="button" className="vz-btn-primary" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" />Créer</button>}
      />

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger dark:border-red-900 dark:bg-red-950/30">{error}</p>
      )}

      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border px-4 py-3 dark:border-ink-800"><h2 className="text-sm font-semibold">Conteneurs</h2></div>
        {isLoading ? (
          <p className="px-4 py-8 text-sm text-cp-muted">Chargement…</p>
        ) : containers.length === 0 ? (
          <EmptyState icon={<Box className="h-8 w-8" />} message="Aucun conteneur Docker." action={<button type="button" className="vz-btn-primary" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" />Créer un conteneur</button>} />
        ) : (
        <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-4 py-2.5 font-semibold">Nom</th>
              <th className="px-4 py-2.5 font-semibold">Image</th>
              <th className="px-4 py-2.5 font-semibold">Ports</th>
              <th className="px-4 py-2.5 font-semibold">État</th>
              <th className="px-4 py-2.5 text-right font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {containers.map((c) => (
              <tr key={c.id} className="border-t border-cp-border/80 transition hover:bg-cp-canvas/50 dark:border-ink-800 dark:hover:bg-ink-900/40">
                <td className="px-4 py-3 font-medium">{c.name}</td>
                <td className="px-4 py-3 font-mono text-xs">{c.image_ref}</td>
                <td className="px-4 py-3 text-xs">
                  {Object.entries(c.ports || {})
                    .map(([h, ct]) => `${h}→${ct}`)
                    .join(", ") || "—"}
                </td>
                <td className="px-4 py-3"><StatusDot status={c.status} /></td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-0.5">
                    {c.status !== "running" ? (
                      <IconAction label={`Démarrer ${c.name}`} disabled={action.isPending}
                        onClick={() => action.mutate({ id: c.id, op: "start", name: c.name })}
                      >
                        <Play className="h-4 w-4" />
                      </IconAction>
                    ) : (
                      <IconAction label={`Arrêter ${c.name}`} disabled={action.isPending}
                        onClick={() => action.mutate({ id: c.id, op: "stop", name: c.name })}
                      >
                        <Square className="h-4 w-4" />
                      </IconAction>
                    )}
                    <IconAction label={`Redémarrer ${c.name}`} disabled={action.isPending}
                      onClick={() => action.mutate({ id: c.id, op: "restart", name: c.name })}
                    >
                      <RefreshCw className="h-4 w-4" />
                    </IconAction>
                    <IconAction label={`Ouvrir les journaux de ${c.name}`} disabled={loadLogs.isPending}
                      onClick={() => loadLogs.mutate(c.id)}
                    >
                      <FileText className="h-4 w-4" />
                    </IconAction>
                    <IconAction label={`Supprimer ${c.name}`} danger
                      onClick={() => {
                        if (window.confirm(`Supprimer ${c.name} ?`)) remove.mutate(c.id);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </IconAction>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        )}
      </div>

      {createOpen && (
        <Modal title="Nouveau conteneur Docker" subtitle="L'image sera téléchargée puis démarrée automatiquement." onClose={() => setCreateOpen(false)}>
          <form className="space-y-3" onSubmit={onCreate}>
            <label className="block text-xs font-medium text-cp-muted">Nom
              <input className="mt-1 vz-input" placeholder="proxy" required autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs font-medium text-cp-muted">Image
                <input className="mt-1 vz-input" required value={form.image} onChange={(e) => setForm({ ...form, image: e.target.value })} />
              </label>
              <label className="block text-xs font-medium text-cp-muted">Tag
                <input className="mt-1 vz-input" value={form.tag} onChange={(e) => setForm({ ...form, tag: e.target.value })} />
              </label>
              <label className="block text-xs font-medium text-cp-muted">Port hôte
                <input className="mt-1 vz-input" value={form.host_port} onChange={(e) => setForm({ ...form, host_port: e.target.value })} />
              </label>
              <label className="block text-xs font-medium text-cp-muted">Port conteneur
                <input className="mt-1 vz-input" value={form.container_port} onChange={(e) => setForm({ ...form, container_port: e.target.value })} />
              </label>
            </div>
            <label className="block text-xs font-medium text-cp-muted">Mémoire (Mo)
              <input className="mt-1 vz-input" type="number" min={64} value={form.memory_mb} onChange={(e) => setForm({ ...form, memory_mb: Number(e.target.value) })} />
            </label>
            <div className="flex justify-end gap-2 pt-1"><button type="button" className="vz-btn-ghost" onClick={() => setCreateOpen(false)}>Annuler</button><button className="vz-btn-primary" type="submit" disabled={create.isPending}>{create.isPending ? "Création…" : "Créer"}</button></div>
          </form>
        </Modal>
      )}

      {logs !== null && (
        <Modal title="Journaux du conteneur" onClose={() => setLogs(null)} wide>
          <pre className="max-h-64 overflow-auto rounded bg-cp-canvas p-3 text-xs dark:bg-ink-900">
            {logs || "(vide)"}
          </pre>
        </Modal>
      )}
    </div>
  );
}
