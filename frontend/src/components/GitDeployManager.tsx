import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";

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
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-cp-muted">
          Git Version Control — clone, pull, deploy keys et webhooks.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Dépôts", value: overview?.repositories ?? "—" },
          { label: "Ready", value: overview?.ready ?? "—" },
          { label: "Erreur", value: overview?.error ?? "—" },
          { label: "Auto-deploy", value: overview?.auto_deploy ?? "—" },
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

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-4" onSubmit={onCreate}>
        <input
          className="vz-input"
          placeholder="nom (ex: webapp)"
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <input
          className="vz-input md:col-span-2"
          placeholder="URL (https://… ou git@…)"
          required
          value={form.remote_url}
          onChange={(e) => setForm({ ...form, remote_url: e.target.value })}
        />
        <div className="flex gap-2">
          <input
            className="vz-input"
            placeholder="branche"
            value={form.branch}
            onChange={(e) => setForm({ ...form, branch: e.target.value })}
          />
          <button className="vz-btn-primary whitespace-nowrap" type="submit" disabled={create.isPending}>
            {create.isPending ? "Clone…" : "Clone"}
          </button>
        </div>
      </form>

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Dépôt</th>
              <th className="px-3 py-2">Branche</th>
              <th className="px-3 py-2">Commit</th>
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
            {repos.map((repo) => (
              <tr key={repo.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2">
                  <div className="font-mono text-xs">{repo.name}</div>
                  <div className="text-xs text-cp-muted">{repo.relative_path}</div>
                </td>
                <td className="px-3 py-2">{repo.branch}</td>
                <td className="px-3 py-2 font-mono text-xs">
                  {repo.last_commit ? repo.last_commit.slice(0, 8) : "—"}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={
                      repo.status === "ready"
                        ? "text-cp-success"
                        : repo.status === "error"
                          ? "text-cp-danger"
                          : "text-cp-muted"
                    }
                  >
                    {repo.status}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      disabled={action.isPending}
                      onClick={() => action.mutate({ id: repo.id, op: "pull", name: repo.name })}
                    >
                      Pull
                    </button>
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => setSelectedKey(repo.deploy_key_public)}
                    >
                      Deploy key
                    </button>
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => {
                        void navigator.clipboard.writeText(repo.webhook_path);
                      }}
                    >
                      Copier webhook
                    </button>
                    <button
                      type="button"
                      className="text-cp-danger hover:underline"
                      onClick={() => {
                        if (window.confirm(`Supprimer ${repo.name} ?`))
                          remove.mutate({ id: repo.id, name: repo.name });
                      }}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && repos.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Aucun dépôt Git.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selectedKey && (
        <div className="vz-panel p-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase text-cp-muted">Deploy key (publique)</h2>
            <button type="button" className="text-cp-link text-sm hover:underline" onClick={() => setSelectedKey(null)}>
              Fermer
            </button>
          </div>
          <pre className="overflow-auto rounded bg-cp-canvas p-3 text-xs dark:bg-ink-900">{selectedKey}</pre>
        </div>
      )}

      <div className="vz-panel overflow-x-auto">
        <div className="border-b border-cp-border bg-cp-canvas px-3 py-2 text-xs font-semibold uppercase text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          Journaux
        </div>
        <table className="min-w-full text-left text-sm">
          <thead>
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
    </div>
  );
}
