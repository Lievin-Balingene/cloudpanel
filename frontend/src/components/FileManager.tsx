import { FormEvent, useCallback, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Folder,
  FileText,
  Upload,
  Trash2,
  Copy,
  ClipboardPaste,
  Scissors,
  Archive,
  Search,
  RefreshCw,
  ChevronRight,
  FilePlus2,
  FolderPlus,
  Pencil,
  Download,
  Shield,
} from "lucide-react";
import { apiRequest, ApiClientError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { formatBytes } from "@/lib/format";

interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  modified_at: string;
  permissions: string;
  mode: number;
  mime: string | null;
  is_text: boolean;
}

interface Listing {
  cwd: string;
  root: string;
  entries: FileEntry[];
}

type ClipMode = "copy" | "cut" | null;

export function FileManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const token = useAuthStore((s) => s.accessToken);
  const role = useAuthStore((s) => s.user?.role);
  const [cwd, setCwd] = useState(() => (role === "administrator" ? "admin" : ""));
  const [selected, setSelected] = useState<string[]>([]);
  const [clipboard, setClipboard] = useState<{ mode: ClipMode; paths: string[] }>({
    mode: null,
    paths: [],
  });
  const [query, setQuery] = useState("");
  const [editor, setEditor] = useState<{ path: string; content: string } | null>(null);
  const [chmodPath, setChmodPath] = useState<string | null>(null);
  const [chmodMode, setChmodMode] = useState("644");
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["files", cwd],
    queryFn: () => apiRequest<Listing>(`/files/?path=${encodeURIComponent(cwd)}`),
  });

  const crumbs = useMemo(() => {
    const parts = cwd ? cwd.split("/").filter(Boolean) : [];
    const items = [{ label: "home", path: "" }];
    let acc = "";
    for (const part of parts) {
      acc = acc ? `${acc}/${part}` : part;
      items.push({ label: part, path: acc });
    }
    return items;
  }, [cwd]);

  const run = useCallback(async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["files"] });
      setSelected([]);
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Opération impossible.";
      setError(message);
    }
  }, [qc]);

  const uploadFiles = async (files: FileList | File[]) => {
    await run(async () => {
      for (const file of Array.from(files)) {
        const body = new FormData();
        body.append("path", cwd);
        body.append("file", file);
        const response = await fetch(`/api/v1/files/upload/`, {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          body,
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new ApiClientError(
            payload?.error?.message ?? `Upload échoué (${response.status})`,
            response.status,
          );
        }
      }
    });
  };

  async function openEditor(entry: FileEntry) {
    if (!entry.is_text && !entry.name.match(/\.(txt|html?|css|js|json|md|py|php|env|conf|ini|yml|yaml|xml|sh|sql|log|csv)$/i)) {
      setError("Prévisualisation texte non disponible pour ce type.");
      return;
    }
    const data = await apiRequest<{ path: string; content: string }>(
      `/files/read/?path=${encodeURIComponent(entry.path)}`,
    );
    setEditor({ path: data.path, content: data.content });
  }

  function toggleSelect(path: string, multi: boolean) {
    setSelected((prev) => {
      if (!multi) return prev.includes(path) && prev.length === 1 ? [] : [path];
      return prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path];
    });
  }

  async function downloadSelected() {
    const files = (data?.entries ?? []).filter((e) => selected.includes(e.path) && !e.is_dir);
    for (const file of files) {
      const response = await fetch(
        `/api/v1/files/download/?path=${encodeURIComponent(file.path)}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
      );
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name;
      a.click();
      URL.revokeObjectURL(url);
    }
  }

  const searchMutation = useMutation({
    mutationFn: () =>
      apiRequest<FileEntry[]>(
        `/files/search/?query=${encodeURIComponent(query)}&path=${encodeURIComponent(cwd)}`,
      ),
  });

  function onCreateFolder(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const name = String(fd.get("name") || "");
    if (!name) return;
    void run(() =>
      apiRequest("/files/mkdir/", {
        method: "POST",
        body: JSON.stringify({ path: cwd, name }),
      }),
    );
    e.currentTarget.reset();
  }

  function onCreateFile(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const name = String(fd.get("name") || "");
    if (!name) return;
    void run(() =>
      apiRequest("/files/create/", {
        method: "POST",
        body: JSON.stringify({ path: cwd, name, content: "" }),
      }),
    );
    e.currentTarget.reset();
  }

  return (
    <div className="space-y-3 animate-fade-up">
      <div className="vz-panel flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="text-sm text-cp-muted">
            Upload, édition, compression, permissions — jailé dans le home du compte.
          </p>
        </div>
        <button type="button" className="vz-btn-ghost" onClick={() => void refetch()}>
          <RefreshCw className="h-4 w-4" />
          Actualiser
        </button>
      </div>

      <div className="vz-panel flex flex-wrap items-center gap-1 px-3 py-2 text-sm">
        {crumbs.map((c, idx) => (
          <span key={c.path || "root"} className="inline-flex items-center gap-1">
            {idx > 0 && <ChevronRight className="h-3.5 w-3.5 text-cp-muted" />}
            <button
              type="button"
              className="rounded px-1.5 py-0.5 hover:bg-cp-orange-soft hover:text-cp-orange-dark"
              onClick={() => setCwd(c.path)}
            >
              {c.label}
            </button>
          </span>
        ))}
      </div>

      <div className="vz-panel flex flex-wrap gap-2 p-3">
        <button type="button" className="vz-btn-primary" onClick={() => fileInputRef.current?.click()}>
          <Upload className="h-4 w-4" />
          Upload
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) void uploadFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          className="vz-btn-ghost"
          disabled={!selected.length}
          onClick={() => setClipboard({ mode: "copy", paths: selected })}
        >
          <Copy className="h-4 w-4" />
          Copier
        </button>
        <button
          type="button"
          className="vz-btn-ghost"
          disabled={!selected.length}
          onClick={() => setClipboard({ mode: "cut", paths: selected })}
        >
          <Scissors className="h-4 w-4" />
          Couper
        </button>
        <button
          type="button"
          className="vz-btn-ghost"
          disabled={!clipboard.mode || !clipboard.paths.length}
          onClick={() =>
            void run(async () => {
              const endpoint = clipboard.mode === "cut" ? "/files/move/" : "/files/copy/";
              await apiRequest(endpoint, {
                method: "POST",
                body: JSON.stringify({ paths: clipboard.paths, destination: cwd }),
              });
              setClipboard({ mode: null, paths: [] });
            })
          }
        >
          <ClipboardPaste className="h-4 w-4" />
          Coller
        </button>
        <button
          type="button"
          className="vz-btn-ghost"
          disabled={!selected.length}
          onClick={() =>
            void run(() =>
              apiRequest("/files/delete/", {
                method: "POST",
                body: JSON.stringify({ paths: selected }),
              }),
            )
          }
        >
          <Trash2 className="h-4 w-4" />
          Supprimer
        </button>
        <button
          type="button"
          className="vz-btn-ghost"
          disabled={!selected.length}
          onClick={() =>
            void run(() =>
              apiRequest("/files/compress/", {
                method: "POST",
                body: JSON.stringify({
                  paths: selected,
                  archive: `${cwd ? `${cwd}/` : ""}archive-${Date.now()}.zip`,
                  format: "zip",
                }),
              }),
            )
          }
        >
          <Archive className="h-4 w-4" />
          Zip
        </button>
        <button
          type="button"
          className="vz-btn-ghost"
          disabled={!selected.length}
          onClick={() => void downloadSelected()}
        >
          <Download className="h-4 w-4" />
          Télécharger
        </button>
        <button
          type="button"
          className="vz-btn-ghost"
          disabled={selected.length !== 1}
          onClick={() => {
            const path = selected[0];
            setChmodPath(path);
            const entry = data?.entries.find((e) => e.path === path);
            if (entry) setChmodMode(entry.mode.toString(8).padStart(3, "0"));
          }}
        >
          <Shield className="h-4 w-4" />
          chmod
        </button>
        <form
          className="ml-auto flex gap-1"
          onSubmit={(e) => {
            e.preventDefault();
            searchMutation.mutate();
          }}
        >
          <input
            className="vz-input w-40"
            placeholder="Rechercher…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="vz-btn-ghost" type="submit">
            <Search className="h-4 w-4" />
          </button>
        </form>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_220px]">
        <div
          className={`vz-panel relative min-h-[420px] overflow-hidden ${dragOver ? "ring-2 ring-cp-orange" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files?.length) void uploadFiles(e.dataTransfer.files);
          }}
        >
          <table className="min-w-full text-left text-sm">
            <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
              <tr>
                <th className="px-3 py-2">Nom</th>
                <th className="px-3 py-2">Taille</th>
                <th className="px-3 py-2">Perms</th>
                <th className="px-3 py-2">Modifié</th>
              </tr>
            </thead>
            <tbody>
              {cwd && (
                <tr
                  className="cursor-pointer border-t border-cp-border hover:bg-cp-orange-soft/40 dark:border-ink-800"
                  onDoubleClick={() => {
                    const parent = cwd.split("/").slice(0, -1).join("/");
                    setCwd(parent);
                  }}
                >
                  <td className="px-3 py-2 font-medium" colSpan={4}>
                    ..
                  </td>
                </tr>
              )}
              {isLoading && (
                <tr>
                  <td className="px-3 py-4" colSpan={4}>
                    Chargement…
                  </td>
                </tr>
              )}
              {(data?.entries ?? []).map((entry) => {
                const active = selected.includes(entry.path);
                return (
                  <tr
                    key={entry.path}
                    className={`cursor-pointer border-t border-cp-border dark:border-ink-800 ${
                      active ? "bg-cp-orange-soft/60" : "hover:bg-cp-canvas dark:hover:bg-ink-900"
                    }`}
                    onClick={(e) => toggleSelect(entry.path, e.ctrlKey || e.metaKey)}
                    onDoubleClick={() => {
                      if (entry.is_dir) {
                        setCwd(entry.path);
                        setSelected([]);
                      } else {
                        void openEditor(entry);
                      }
                    }}
                  >
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-2">
                        {entry.is_dir ? (
                          <Folder className="h-4 w-4 text-cp-orange" />
                        ) : (
                          <FileText className="h-4 w-4 text-cp-link" />
                        )}
                        {entry.name}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-cp-muted">
                      {entry.is_dir ? "—" : formatBytes(entry.size)}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{entry.permissions}</td>
                    <td className="px-3 py-2 text-xs text-cp-muted">
                      {new Date(entry.modified_at).toLocaleString("fr-FR")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {dragOver && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-cp-orange/10 text-sm font-semibold text-cp-orange-dark">
              Déposez les fichiers ici
            </div>
          )}
        </div>

        <div className="space-y-3">
          <form className="vz-panel space-y-2 p-3" onSubmit={onCreateFolder}>
            <p className="text-xs font-semibold uppercase text-cp-muted">Nouveau dossier</p>
            <input className="vz-input" name="name" placeholder="nom" required />
            <button className="vz-btn-ghost w-full" type="submit">
              <FolderPlus className="h-4 w-4" />
              Créer
            </button>
          </form>
          <form className="vz-panel space-y-2 p-3" onSubmit={onCreateFile}>
            <p className="text-xs font-semibold uppercase text-cp-muted">Nouveau fichier</p>
            <input className="vz-input" name="name" placeholder="index.html" required />
            <button className="vz-btn-ghost w-full" type="submit">
              <FilePlus2 className="h-4 w-4" />
              Créer
            </button>
          </form>
          {selected.length === 1 && (
            <div className="vz-panel space-y-2 p-3">
              <p className="text-xs font-semibold uppercase text-cp-muted">Actions</p>
              <button
                type="button"
                className="vz-btn-ghost w-full"
                onClick={() => {
                  const entry = data?.entries.find((e) => e.path === selected[0]);
                  if (entry && !entry.is_dir) void openEditor(entry);
                }}
              >
                <Pencil className="h-4 w-4" />
                Éditer
              </button>
              <button
                type="button"
                className="vz-btn-ghost w-full"
                onClick={() => {
                  const entry = data?.entries.find((e) => e.path === selected[0]);
                  if (!entry) return;
                  if (entry.name.match(/\.(zip|tar\.gz|tgz|tar)$/i)) {
                    void run(() =>
                      apiRequest("/files/decompress/", {
                        method: "POST",
                        body: JSON.stringify({ archive: entry.path, destination: cwd }),
                      }),
                    );
                  }
                }}
              >
                <Archive className="h-4 w-4" />
                Décompresser
              </button>
              <button
                type="button"
                className="vz-btn-ghost w-full"
                onClick={() => {
                  const name = window.prompt("Nouveau nom ?");
                  if (!name) return;
                  void run(() =>
                    apiRequest("/files/rename/", {
                      method: "POST",
                      body: JSON.stringify({ path: selected[0], new_name: name }),
                    }),
                  );
                }}
              >
                Renommer
              </button>
            </div>
          )}
        </div>
      </div>

      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
          {error}
        </p>
      )}

      {searchMutation.data && (
        <div className="vz-panel p-3">
          <p className="mb-2 text-sm font-semibold">Résultats ({searchMutation.data.length})</p>
          <ul className="space-y-1 text-sm">
            {searchMutation.data.map((item) => (
              <li key={item.path}>
                <button
                  type="button"
                  className="text-cp-link hover:underline"
                  onClick={() => {
                    if (item.is_dir) setCwd(item.path);
                    else {
                      const parent = item.path.split("/").slice(0, -1).join("/");
                      setCwd(parent);
                      setSelected([item.path]);
                    }
                  }}
                >
                  {item.path || item.name}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {editor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="flex h-[80vh] w-full max-w-4xl flex-col rounded border border-cp-border bg-white shadow-xl dark:border-ink-700 dark:bg-ink-950">
            <div className="flex items-center justify-between border-b border-cp-border px-4 py-3 dark:border-ink-800">
              <p className="font-semibold">{editor.path}</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="vz-btn-primary"
                  onClick={() =>
                    void run(async () => {
                      await apiRequest("/files/write/", {
                        method: "PUT",
                        body: JSON.stringify({ path: editor.path, content: editor.content }),
                      });
                      setEditor(null);
                    })
                  }
                >
                  Enregistrer
                </button>
                <button type="button" className="vz-btn-ghost" onClick={() => setEditor(null)}>
                  Fermer
                </button>
              </div>
            </div>
            <textarea
              className="min-h-0 flex-1 resize-none bg-cp-canvas p-4 font-mono text-sm outline-none dark:bg-ink-900"
              value={editor.content}
              onChange={(e) => setEditor({ ...editor, content: e.target.value })}
              spellCheck={false}
            />
          </div>
        </div>
      )}

      {chmodPath && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950">
            <p className="mb-3 font-semibold">Permissions — {chmodPath}</p>
            <input
              className="vz-input mb-3"
              value={chmodMode}
              onChange={(e) => setChmodMode(e.target.value)}
              placeholder="755"
            />
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setChmodPath(null)}>
                Annuler
              </button>
              <button
                type="button"
                className="vz-btn-primary"
                onClick={() =>
                  void run(async () => {
                    await apiRequest("/files/chmod/", {
                      method: "POST",
                      body: JSON.stringify({ path: chmodPath, mode: chmodMode }),
                    });
                    setChmodPath(null);
                  })
                }
              >
                Appliquer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
