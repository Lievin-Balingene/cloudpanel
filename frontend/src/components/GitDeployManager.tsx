import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  GitPullRequest,
  Home,
  Key,
  Plus,
  Trash2,
  Webhook,
} from "lucide-react";
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

interface FileListing {
  cwd: string;
  root: string;
  entries: Array<{ name: string; path: string; is_dir: boolean }>;
}

const EMPTY_FORM = {
  name: "",
  remote_url: "",
  branch: "main",
  parent_path: "repositories",
  folder_name: "",
};

function sanitizeSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]/g, "")
    .slice(0, 48);
}

function joinRel(parent: string, folder: string): string {
  const p = parent.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  const f = folder.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  if (!f) return p;
  if (!p) return f;
  return `${p}/${f}`;
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

  const [form, setForm] = useState(EMPTY_FORM);
  const [pathTouched, setPathTouched] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [browseCwd, setBrowseCwd] = useState("");
  const [error, setError] = useState<string | null>(null);

  const folderName = form.folder_name.trim() || sanitizeSlug(form.name) || "projet";
  const relativePath = joinRel(form.parent_path, folderName);

  const { data: listing, isFetching: listingLoading } = useQuery({
    queryKey: ["git-folder-browse", browseCwd],
    queryFn: () =>
      apiRequest<FileListing>(`/files/?path=${encodeURIComponent(browseCwd)}`),
    enabled: browseOpen,
  });

  const folders = useMemo(
    () => (listing?.entries || []).filter((e) => e.is_dir),
    [listing],
  );

  const breadcrumbs = useMemo(() => {
    const cwd = listing?.cwd ?? browseCwd;
    if (!cwd) return [] as string[];
    return cwd.split("/").filter(Boolean);
  }, [listing?.cwd, browseCwd]);

  useEffect(() => {
    if (!createOpen || pathTouched) return;
    const slug = sanitizeSlug(form.name);
    if (slug) {
      setForm((f) => (f.folder_name === slug ? f : { ...f, folder_name: slug }));
    }
  }, [form.name, createOpen, pathTouched]);

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
            body: JSON.stringify({
              name: form.name,
              remote_url: form.remote_url,
              branch: form.branch || "main",
              relative_path: relativePath,
              clone_now: true,
            }),
          }),
        {
          detail: `${form.remote_url} → ~/${relativePath}`,
          tickDetail: (ms) =>
            ms < 2500
              ? "Connexion au dépôt distant…"
              : ms < 7000
                ? `Clone vers ${relativePath}…`
                : "Indexation et finalisation…",
        },
      ),
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setPathTouched(false);
      setError(null);
      setCreateOpen(false);
      setBrowseOpen(false);
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
          tickDetail: (ms) => (ms < 2000 ? `Exécution ${op}…` : "Synchronisation…"),
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
    if (!relativePath) {
      setError("Choisissez un dossier de destination.");
      return;
    }
    create.mutate();
  }

  function openCreate() {
    setForm(EMPTY_FORM);
    setPathTouched(false);
    setError(null);
    setBrowseOpen(false);
    setBrowseCwd("repositories");
    setCreateOpen(true);
  }

  function selectParent(path: string) {
    setPathTouched(true);
    setForm((f) => ({ ...f, parent_path: path.replace(/^\/+|\/+$/g, "") }));
    setBrowseOpen(false);
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Clonez un projet Git et déployez-le dans votre espace."
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
            <button type="button" className="vz-btn-primary" onClick={openCreate}>
              <Plus className="h-4 w-4" />
              Créer
            </button>
          </>
        }
      />

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger dark:border-red-900 dark:bg-red-950/30">
          {error}
        </p>
      )}

      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border px-4 py-3 dark:border-ink-800">
          <h2 className="text-sm font-semibold">Dépôts</h2>
        </div>
        {isLoading ? (
          <p className="px-4 py-8 text-sm text-cp-muted">Chargement…</p>
        ) : repos.length === 0 ? (
          <EmptyState
            icon={<GitPullRequest className="h-8 w-8" />}
            message="Aucun dépôt Git."
            action={
              <button type="button" className="vz-btn-primary" onClick={openCreate}>
                <Plus className="h-4 w-4" />
                Cloner un dépôt
              </button>
            }
          />
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
                  <tr
                    key={repo.id}
                    className="border-t border-cp-border/80 transition hover:bg-cp-canvas/50 dark:border-ink-800 dark:hover:bg-ink-900/40"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium">{repo.name}</div>
                      <div className="flex items-center gap-1 text-xs text-cp-muted">
                        <FolderOpen className="h-3 w-3 shrink-0 text-cp-orange" />
                        <span className="font-mono">{repo.relative_path}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">{repo.branch}</td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {repo.last_commit ? repo.last_commit.slice(0, 8) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <StatusDot
                        status={repo.status === "ready" ? "ok" : repo.status}
                        label={repo.status === "ready" ? "Prêt" : undefined}
                      />
                      {repo.last_error ? (
                        <p
                          className="mt-1 max-w-xs truncate text-[11px] text-cp-danger"
                          title={repo.last_error}
                        >
                          {repo.last_error}
                        </p>
                      ) : null}
                    </td>
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
        <Modal
          title="Cloner un dépôt Git"
          subtitle="Choisissez le dossier où le projet sera placé dans votre home."
          onClose={() => {
            setCreateOpen(false);
            setBrowseOpen(false);
          }}
          wide={browseOpen}
        >
          <form className="space-y-3" onSubmit={onCreate}>
            <label className="block text-xs font-medium text-cp-muted">
              Nom
              <input
                className="mt-1 vz-input"
                placeholder="webapp"
                required
                autoFocus
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <label className="block text-xs font-medium text-cp-muted">
              URL distante
              <input
                className="mt-1 vz-input"
                placeholder="https://… ou git@…"
                required
                value={form.remote_url}
                onChange={(e) => setForm({ ...form, remote_url: e.target.value })}
              />
            </label>
            <label className="block text-xs font-medium text-cp-muted">
              Branche
              <input
                className="mt-1 vz-input"
                placeholder="main"
                value={form.branch}
                onChange={(e) => setForm({ ...form, branch: e.target.value })}
              />
            </label>

            <div className="space-y-2 rounded-lg border border-cp-border bg-cp-canvas/40 p-3 dark:border-ink-800 dark:bg-ink-900/40">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-semibold text-cp-navy dark:text-cp-orange">
                  Dossier de destination
                </p>
                <div className="flex flex-wrap gap-1">
                  {(
                    [
                      { parent: "repositories", folder: null as string | null, label: "repositories/" },
                      { parent: "", folder: "public_html", label: "public_html" },
                      { parent: "public_html", folder: null, label: "public_html/…" },
                      { parent: "", folder: null, label: "~/ racine" },
                    ] as const
                  ).map((preset) => {
                    const active =
                      form.parent_path === preset.parent &&
                      (preset.folder === null || form.folder_name === preset.folder);
                    return (
                      <button
                        key={preset.label}
                        type="button"
                        className={`rounded border px-2 py-0.5 text-[11px] ${
                          active
                            ? "border-cp-orange bg-cp-orange-soft text-cp-navy"
                            : "border-cp-border text-cp-muted hover:bg-white dark:hover:bg-ink-950"
                        }`}
                        onClick={() => {
                          setPathTouched(true);
                          setForm((f) => ({
                            ...f,
                            parent_path: preset.parent,
                            folder_name:
                              preset.folder !== null
                                ? preset.folder
                                : sanitizeSlug(f.name) || f.folder_name,
                          }));
                        }}
                      >
                        {preset.label}
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    className="vz-btn-ghost !px-2 !py-0.5 text-[11px]"
                    onClick={() => {
                      setBrowseCwd(form.parent_path || "");
                      setBrowseOpen((v) => !v);
                    }}
                  >
                    <FolderOpen className="h-3 w-3" />
                    {browseOpen ? "Fermer" : "Parcourir…"}
                  </button>
                </div>
              </div>

              <label className="block text-xs font-medium text-cp-muted">
                Dossier parent (dans le home)
                <div className="mt-1 flex overflow-hidden rounded-lg border border-cp-border focus-within:border-cp-link focus-within:ring-2 focus-within:ring-cp-link/20 dark:border-ink-700">
                  <span className="flex items-center border-r border-cp-border bg-white px-2 font-mono text-[11px] text-cp-muted dark:border-ink-700 dark:bg-ink-950">
                    ~/
                  </span>
                  <input
                    className="vz-input !rounded-none !border-0 !ring-0"
                    placeholder="repositories"
                    value={form.parent_path}
                    onChange={(e) => {
                      setPathTouched(true);
                      setForm({
                        ...form,
                        parent_path: e.target.value.replace(/\\/g, "/").replace(/^\/+/, ""),
                      });
                    }}
                  />
                </div>
              </label>

              <label className="block text-xs font-medium text-cp-muted">
                Nom du dossier projet
                <input
                  className="mt-1 vz-input font-mono"
                  placeholder={sanitizeSlug(form.name) || "mon-projet"}
                  value={form.folder_name}
                  onChange={(e) => {
                    setPathTouched(true);
                    setForm({
                      ...form,
                      folder_name: e.target.value.replace(/\\/g, "/").replace(/^\/+|\/+$/g, ""),
                    });
                  }}
                />
              </label>

              <p className="rounded-md bg-white px-2.5 py-2 font-mono text-xs text-cp-navy dark:bg-ink-950 dark:text-cp-orange">
                Destination finale :{" "}
                <strong className="font-semibold">~/{relativePath || "…"}</strong>
              </p>
              <p className="text-[11px] text-cp-muted">
                Le clone créera ce dossier (il doit être absent ou vide). Ex.{" "}
                <code className="font-mono">public_html</code> pour remplacer le site web, ou{" "}
                <code className="font-mono">repositories/webapp</code>.
              </p>

              {browseOpen && (
                <div className="overflow-hidden rounded-lg border border-cp-border bg-white dark:border-ink-700 dark:bg-ink-950">
                  <div className="flex flex-wrap items-center gap-1 border-b border-cp-border px-2 py-1.5 text-[11px] dark:border-ink-800">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-cp-canvas dark:hover:bg-ink-900"
                      onClick={() => setBrowseCwd("")}
                      title="Racine du home"
                    >
                      <Home className="h-3 w-3" />
                      ~
                    </button>
                    {breadcrumbs.map((part, idx) => {
                      const path = breadcrumbs.slice(0, idx + 1).join("/");
                      return (
                        <span key={path} className="inline-flex items-center gap-1">
                          <ChevronRight className="h-3 w-3 text-cp-muted" />
                          <button
                            type="button"
                            className="rounded px-1.5 py-0.5 font-mono hover:bg-cp-canvas dark:hover:bg-ink-900"
                            onClick={() => setBrowseCwd(path)}
                          >
                            {part}
                          </button>
                        </span>
                      );
                    })}
                    <button
                      type="button"
                      className="vz-btn-primary ml-auto !px-2 !py-0.5 text-[11px]"
                      onClick={() => selectParent(listing?.cwd ?? browseCwd)}
                    >
                      Sélectionner ce dossier
                    </button>
                  </div>
                  <ul className="max-h-48 overflow-auto text-sm">
                    {listingLoading && (
                      <li className="px-3 py-4 text-xs text-cp-muted">Chargement…</li>
                    )}
                    {!listingLoading && folders.length === 0 && (
                      <li className="px-3 py-4 text-xs text-cp-muted">
                        Aucun sous-dossier — vous pouvez sélectionner ce niveau.
                      </li>
                    )}
                    {folders.map((dir) => (
                      <li key={dir.path}>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-cp-orange-soft/50 dark:hover:bg-ink-900"
                          onClick={() => setBrowseCwd(dir.path)}
                          onDoubleClick={() => selectParent(dir.path)}
                        >
                          <Folder className="h-4 w-4 shrink-0 text-cp-orange" />
                          <span className="font-mono text-xs">{dir.name}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                className="vz-btn-ghost"
                onClick={() => {
                  setCreateOpen(false);
                  setBrowseOpen(false);
                }}
              >
                Annuler
              </button>
              <button className="vz-btn-primary" type="submit" disabled={create.isPending}>
                {create.isPending ? "Clonage…" : "Cloner"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {selectedKey && (
        <Modal title="Clé de déploiement publique" onClose={() => setSelectedKey(null)} wide>
          <pre className="overflow-auto rounded bg-cp-canvas p-3 text-xs dark:bg-ink-900">{selectedKey}</pre>
        </Modal>
      )}

      {logsOpen && (
        <Modal
          title="Journaux de déploiement"
          subtitle="Les 30 derniers événements."
          onClose={() => setLogsOpen(false)}
          wide
        >
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
