import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Play, Plus, RefreshCw, Square, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot } from "@/components/ui/PageChrome";

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
  const [createOpen, setCreateOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["node-overview"] });
    void qc.invalidateQueries({ queryKey: ["node-apps"] });
  };

  const create = useMutation({
    mutationFn: () =>
      runWithProgress(
        `Création app Node · ${form.name || "app"}`,
        () => apiRequest("/node/apps/", { method: "POST", body: JSON.stringify(form) }),
        {
          tickDetail: (ms) =>
            ms < 2500 ? "Préparation du runtime…" : "Configuration du process…",
        },
      ),
    onSuccess: () => {
      setForm({ name: "", framework: "generic", node_version: "20", domain_name: "" });
      setError(null);
      setCreateOpen(false);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const action = useMutation({
    mutationFn: ({ id, op, name }: { id: number; op: string; name: string }) =>
      runWithProgress(`Node ${op} · ${name}`, () =>
        apiRequest(`/node/apps/${id}/${op}/`, { method: "POST", body: "{}" }),
      ),
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
      <PageHeader
        title={title}
        subtitle="Applications Node.js — package.json, npm install, démarrage et journaux."
        stats={[
          { label: "Applications", value: overview?.apps ?? "—" },
          { label: "En cours", value: overview?.running ?? "—" },
          { label: "Arrêtées", value: overview?.stopped ?? "—" },
          { label: "Erreurs", value: overview?.error ?? "—" },
        ]}
        actions={
          <button type="button" className="vz-btn-primary" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            Créer
          </button>
        }
      />

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger dark:border-red-900 dark:bg-red-950/30">{error}</p>
      )}

      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border px-4 py-3 dark:border-ink-800">
          <h2 className="text-sm font-semibold">Applications</h2>
        </div>
        {isLoading ? (
          <p className="px-4 py-8 text-sm text-cp-muted">Chargement…</p>
        ) : apps.length === 0 ? (
          <EmptyState
            icon={<FileText className="h-8 w-8" />}
            message="Aucune application Node.js."
            action={
              <button type="button" className="vz-btn-primary" onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" />
                Créer une application
              </button>
            }
          />
        ) : (
        <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-4 py-2.5 font-semibold">Application</th>
              <th className="px-4 py-2.5 font-semibold">Chemin</th>
              <th className="px-4 py-2.5 font-semibold">Port</th>
              <th className="px-4 py-2.5 font-semibold">État</th>
              <th className="px-4 py-2.5 text-right font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {apps.map((app) => (
              <tr key={app.id} className="border-t border-cp-border/80 transition hover:bg-cp-canvas/50 dark:border-ink-800 dark:hover:bg-ink-900/40">
                <td className="px-4 py-3">
                  <div className="font-medium">{app.name}</div>
                  <div className="text-xs text-cp-muted">
                    {app.framework} · node{app.node_version}
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs">{app.relative_root}</td>
                <td className="px-4 py-3 tabular-nums">{app.port}</td>
                <td className="px-4 py-3"><StatusDot status={app.status} /></td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-0.5">
                    {app.status !== "running" ? (
                      <IconAction
                        label={`Démarrer ${app.name}`}
                        disabled={action.isPending}
                        onClick={() => action.mutate({ id: app.id, op: "start", name: app.name })}
                      >
                        <Play className="h-4 w-4" />
                      </IconAction>
                    ) : (
                      <IconAction
                        label={`Arrêter ${app.name}`}
                        disabled={action.isPending}
                        onClick={() => action.mutate({ id: app.id, op: "stop", name: app.name })}
                      >
                        <Square className="h-4 w-4" />
                      </IconAction>
                    )}
                    <IconAction
                      label={`Redémarrer ${app.name}`}
                      disabled={action.isPending}
                      onClick={() => action.mutate({ id: app.id, op: "restart", name: app.name })}
                    >
                      <RefreshCw className="h-4 w-4" />
                    </IconAction>
                    <IconAction
                      label={`Installer les dépendances de ${app.name}`}
                      disabled={action.isPending}
                      onClick={() => action.mutate({ id: app.id, op: "install", name: app.name })}
                    >
                      <Download className="h-4 w-4" />
                    </IconAction>
                    <IconAction
                      label={`Ouvrir les journaux de ${app.name}`}
                      disabled={loadLogs.isPending}
                      onClick={() => loadLogs.mutate(app.id)}
                    >
                      <FileText className="h-4 w-4" />
                    </IconAction>
                    <IconAction
                      label={`Supprimer ${app.name}`}
                      danger
                      onClick={() => {
                        if (window.confirm(`Supprimer ${app.name} ?`)) remove.mutate(app.id);
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
        <Modal title="Nouvelle application Node.js" subtitle="Le runtime et le process seront configurés automatiquement." onClose={() => setCreateOpen(false)}>
          <form className="space-y-3" onSubmit={onCreate}>
            <label className="block text-xs font-medium text-cp-muted">Nom
              <input className="mt-1 vz-input" placeholder="api" required autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="block text-xs font-medium text-cp-muted">Framework
              <select className="mt-1 vz-input" value={form.framework} onChange={(e) => setForm({ ...form, framework: e.target.value })}>
                <option value="generic">Générique</option><option value="express">Express</option><option value="nest">NestJS</option><option value="next">Next.js</option>
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs font-medium text-cp-muted">Version Node
                <input className="mt-1 vz-input" value={form.node_version} onChange={(e) => setForm({ ...form, node_version: e.target.value })} />
              </label>
              <label className="block text-xs font-medium text-cp-muted">Domaine (facultatif)
                <input className="mt-1 vz-input" value={form.domain_name} onChange={(e) => setForm({ ...form, domain_name: e.target.value })} />
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-1"><button type="button" className="vz-btn-ghost" onClick={() => setCreateOpen(false)}>Annuler</button><button className="vz-btn-primary" type="submit" disabled={create.isPending}>{create.isPending ? "Création…" : "Créer"}</button></div>
          </form>
        </Modal>
      )}

      {logs && (
        <Modal title="Journaux de l'application" onClose={() => setLogs(null)} wide>
          {Object.entries(logs).map(([name, content]) => (
            <div key={name} className="mb-3">
              <p className="mb-1 font-mono text-xs text-cp-orange">{name}</p>
              <pre className="max-h-48 overflow-auto rounded bg-cp-canvas p-3 text-xs dark:bg-ink-900">
                {content || "(vide)"}
              </pre>
            </div>
          ))}
        </Modal>
      )}
    </div>
  );
}
