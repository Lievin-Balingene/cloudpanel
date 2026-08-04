import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, GitPullRequest, Key, Plus, Trash2, Webhook } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot } from "@/components/ui/PageChrome";

interface GitOverview {
  repositories: number;
  ready: number;
  error: number;
  auto_deploy: number;
  provision_mode: string;
}

interface GitRepo {
  id: number;
  name: string;
  label: string;
  remote_url: string;
  branch: string;
  relative_path: string;
  status: string;
  last_commit: string;
  last_commit_message: string;
  deploy_key_public: string;
  webhook_path: string;
  auto_deploy: boolean;
  last_error: string;
}

interface GitLog {
  id: number;
  repository_name: string;
  event_type: string;
  success: boolean;
  message: string;
  commit_hash: string;
  created_at: string;
}

export function GitDeployManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["git-overview"],
    queryFn: () => apiRequest<GitOverview>("/git/overview/"),
  });
  const { data: repos = [], isLoading } = useQuery({
    queryKey: ["git-repos"],
    queryFn: () => apiRequest<GitRepo[]>("/git/repos/"),
  });
  const { data: logs = [] } = useQuery({
    queryKey: ["git-logs"],
    queryFn: () => apiRequest<GitLog[]>("/git/logs/"),
  });

  const [form, setForm] = useState({
    name: "",
    remote_url: "",
    branch: "main",
  });
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["git-overview"] });
    void qc.invalidateQueries({ queryKey: ["git-repos"] });
    void qc.invalidateQueries({ queryKey: ["git-logs"] });
  };

  const create = useMutation({
    mutationFn: () =>
      runWithProgress(
        `Clone Git · ${form.name || "dépôt"}`,
        () =>
          apiRequest("/git/repos/", {
            method: "POST",
            body: JSON.stringify({ ...form, clone_now: true }),
          }),
        {
          detail: form.remote_url,
          tickDetail: (ms) =>
            ms < 2500
              ? "Connexion au dépôt distant…"
              : ms < 7000
                ? "Clone en cours…"
                : "Indexation et finalisation…",
        },
      ),
    onSuccess: () => {
      setForm({ name: "", remote_url: "", branch: "main" });
      setError(null);
      setCreateOpen(false);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const action = useMutation({
    mutationFn: ({ id, op, name }: { id: number; op: string; name: string }) =>
      runWithProgress(
        `Git ${op} · ${name}`,
        () => apiRequest(`/git/repos/${id}/${op}/`, { method: "POST", body: "{}" }),
        {
          tickDetail: (ms) =>
            ms < 2000 ? `Exécution ${op}…` : "Synchronisation…",
        },
      ),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      runWithProgress(`Suppression Git · ${name}`, () =>
        apiRequest(`/git/repos/${id}/?remove_files=true`, { method: "DELETE" }),
      ),
    onSuccess: invalidate,
  });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Clonez des dépôts, récupérez les mises à jour et configurez clés de déploiement et webhooks."
        stats={[
          { label: "Dépôts", value: overview?.repositories ?? "—" },
          { label: "Prêts", value: overview?.ready ?? "—" },
          { label: "Erreurs", value: overview?.error ?? "—" },
          { label: "Auto-déploiement", value: overview?.auto_deploy ?? "—" },
        ]}
        actions={
          <>
            <IconAction label="Consulter les journaux de déploiement" onClick={() => setLogsOpen(true)}>
              <FileText className="h-4 w-4" />
            </IconAction>
            <button type="button" className="vz-btn-primary" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" />
              Créer
            </button>
          </>
        }
      />

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger dark:border-red-900 dark:bg-red-950/30">{error}</p>
      )}

      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border px-4 py-3 dark:border-ink-800"><h2 className="text-sm font-semibold">Dépôts</h2></div>
        {isLoading ? (
          <p className="px-4 py-8 text-sm text-cp-muted">Chargement…</p>
        ) : repos.length === 0 ? (
          <EmptyState icon={<GitPullRequest className="h-8 w-8" />} message="Aucun dépôt Git." action={<button type="button" className="vz-btn-primary" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" />Cloner un dépôt</button>} />
        ) : (
        <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-4 py-2.5 font-semibold">Dépôt</th>
              <th className="px-4 py-2.5 font-semibold">Branche</th>
              <th className="px-4 py-2.5 font-semibold">Commit</th>
              <th className="px-4 py-2.5 font-semibold">État</th>
              <th className="px-4 py-2.5 text-right font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {repos.map((repo) => (
              <tr key={repo.id} className="border-t border-cp-border/80 transition hover:bg-cp-canvas/50 dark:border-ink-800 dark:hover:bg-ink-900/40">
                <td className="px-4 py-3">
                  <div className="font-medium">{repo.name}</div>
                  <div className="text-xs text-cp-muted">{repo.relative_path}</div>
                </td>
                <td className="px-4 py-3">{repo.branch}</td>
                <td className="px-4 py-3 font-mono text-xs">
                  {repo.last_commit ? repo.last_commit.slice(0, 8) : "—"}
                </td>
                <td className="px-4 py-3"><StatusDot status={repo.status === "ready" ? "ok" : repo.status} label={repo.status === "ready" ? "Prêt" : undefined} /></td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-0.5">
                    <IconAction
                      label={`Récupérer les mises à jour de ${repo.name}`}
                      disabled={action.isPending}
                      onClick={() => action.mutate({ id: repo.id, op: "pull", name: repo.name })}
                    >
                      <GitPullRequest className="h-4 w-4" />
                    </IconAction>
                    <IconAction
                      label={`Afficher la clé de déploiement de ${repo.name}`}
                      onClick={() => setSelectedKey(repo.deploy_key_public)}
                    >
                      <Key className="h-4 w-4" />
                    </IconAction>
                    <IconAction
                      label={`Copier le webhook de ${repo.name}`}
                      onClick={() => {
                        void navigator.clipboard.writeText(repo.webhook_path);
                      }}
                    >
                      <Webhook className="h-4 w-4" />
                    </IconAction>
                    <IconAction
                      label={`Supprimer ${repo.name}`}
                      danger
                      onClick={() => {
                        if (window.confirm(`Supprimer ${repo.name} ?`))
                          remove.mutate({ id: repo.id, name: repo.name });
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
        <Modal title="Cloner un dépôt Git" subtitle="Le dépôt distant sera cloné dans votre espace web." onClose={() => setCreateOpen(false)}>
          <form className="space-y-3" onSubmit={onCreate}>
            <label className="block text-xs font-medium text-cp-muted">Nom
              <input className="mt-1 vz-input" placeholder="webapp" required autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="block text-xs font-medium text-cp-muted">URL distante
              <input className="mt-1 vz-input" placeholder="https://… ou git@…" required value={form.remote_url} onChange={(e) => setForm({ ...form, remote_url: e.target.value })} />
            </label>
            <label className="block text-xs font-medium text-cp-muted">Branche
              <input className="mt-1 vz-input" placeholder="main" value={form.branch} onChange={(e) => setForm({ ...form, branch: e.target.value })} />
            </label>
            <div className="flex justify-end gap-2 pt-1"><button type="button" className="vz-btn-ghost" onClick={() => setCreateOpen(false)}>Annuler</button><button className="vz-btn-primary" type="submit" disabled={create.isPending}>{create.isPending ? "Clonage…" : "Cloner"}</button></div>
          </form>
        </Modal>
      )}

      {selectedKey && (
        <Modal title="Clé de déploiement publique" onClose={() => setSelectedKey(null)} wide>
          <pre className="overflow-auto rounded bg-cp-canvas p-3 text-xs dark:bg-ink-900">{selectedKey}</pre>
        </Modal>
      )}

      {logsOpen && (
        <Modal title="Journaux de déploiement" subtitle="Les 30 derniers événements." onClose={() => setLogsOpen(false)} wide>
        <div className="max-h-[60vh] overflow-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr className="text-xs uppercase text-cp-muted">
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Repo</th>
              <th className="px-3 py-2">Événement</th>
              <th className="px-3 py-2">Message</th>
            </tr>
          </thead>
          <tbody>
            {logs.slice(0, 30).map((log) => (
              <tr key={log.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 text-xs">
                  {new Date(log.created_at).toLocaleString("fr-FR")}
                </td>
                <td className="px-3 py-2">{log.repository_name}</td>
                <td className="px-3 py-2 font-mono text-xs">{log.event_type}</td>
                <td className={`px-3 py-2 text-xs ${log.success ? "" : "text-cp-danger"}`}>
                  {log.message || "—"}
                </td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={4}>
                  Aucun journal.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
        </Modal>
      )}
    </div>
  );
}
