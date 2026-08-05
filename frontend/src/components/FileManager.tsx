import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
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
  X,
} from "lucide-react";
import { apiRequest, ApiClientError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { formatBytes } from "@/lib/format";
import {
  collectDataTransferJobs,
  FILES_BROADCAST,
  openUploadTab,
  resolvePanelBase,
  UPLOAD_MSG,
} from "@/lib/fileUpload";

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

type ConfirmState = {
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void | Promise<void>;
};

function ConfirmDialog({
  state,
  busy,
  onCancel,
}: {
  state: ConfirmState;
  busy: boolean;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4">
      <div
        className="w-full max-w-md rounded border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
      >
        <h2 id="confirm-title" className="text-base font-semibold text-cp-text">
          {state.title}
        </h2>
        <p className="mt-2 text-sm text-cp-muted whitespace-pre-wrap">{state.message}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="vz-btn-ghost" disabled={busy} onClick={onCancel}>
            Annuler
          </button>
          <button
            type="button"
            className={state.danger ? "vz-btn-primary bg-cp-danger hover:opacity-90" : "vz-btn-primary"}
            disabled={busy}
            onClick={() => void state.onConfirm()}
          >
            {busy ? "…" : state.confirmLabel ?? "Confirmer"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function FileManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const location = useLocation();
  const panelBase = resolvePanelBase(location.pathname);
  const token = useAuthStore((s) => s.accessToken);
  const role = useAuthStore((s) => s.user?.role);
  const [cwd, setCwd] = useState(() => (role === "administrator" ? "admin" : ""));
  const [selected, setSelected] = useState<string[]>([]);
  const [clipboard, setClipboard] = useState<{ mode: ClipMode; paths: string[] }>({
    mode: null,
    paths: [],
  });
  const [query, setQuery] = useState("");
  const [editor, setEditor] = useState<{ path: string; content: string; original: string } | null>(
    null,
  );
  const [chmodPath, setChmodPath] = useState<string | null>(null);
  const [chmodMode, setChmodMode] = useState("644");
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [renameOpen, setRenameOpen] = useState(false);
  const [dropTargetPath, setDropTargetPath] = useState<string | null>(null);
  const [internalDrag, setInternalDrag] = useState(false);
  const dragDepth = useRef(0);
  const lastClickedRef = useRef<string | null>(null);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["files", cwd],
    queryFn: () => apiRequest<Listing>(`/files/?path=${encodeURIComponent(cwd)}`),
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  });

  const entryPaths = useMemo(
    () => (data?.entries ?? []).map((e) => e.path),
    [data?.entries],
  );
  const allSelected =
    entryPaths.length > 0 && entryPaths.every((p) => selected.includes(p));
  const someSelected = selected.some((p) => entryPaths.includes(p));

  useEffect(() => {
    setSelected([]);
    lastClickedRef.current = null;
  }, [cwd]);

  useEffect(() => {
    const onDone = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type === UPLOAD_MSG.DONE) {
        void qc.invalidateQueries({ queryKey: ["files"] });
      }
    };
    window.addEventListener("message", onDone);
    let bc: BroadcastChannel | null = null;
    try {
      bc = new BroadcastChannel(FILES_BROADCAST);
      bc.onmessage = (event) => {
        if (event.data?.type === "invalidate") {
          void qc.invalidateQueries({ queryKey: ["files"] });
        }
      };
    } catch {
      /* ignore */
    }
    return () => {
      window.removeEventListener("message", onDone);
      bc?.close();
    };
  }, [qc]);

  const launchUpload = useCallback(
    (
      dest: string,
      options?: { jobs?: import("@/lib/fileUpload").DropJob[]; preferFolder?: boolean },
    ) => {
      const win = openUploadTab(panelBase, dest, options);
      if (!win) {
        setError(
          "Impossible d'ouvrir l'onglet d'upload. Autorisez les pop-ups pour ce site, puis réessayez.",
        );
      }
    },
    [panelBase],
  );

  const launchUploadJobs = useCallback(
    async (dest: string, collect: () => ReturnType<typeof collectDataTransferJobs>) => {
      try {
        const jobs = await collect();
        if (!jobs.length) return;
        launchUpload(dest, { jobs });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Impossible de lire le dépôt.");
      }
    },
    [launchUpload],
  );
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

  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
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
        throw err;
      }
    },
    [qc],
  );

  const askConfirm = useCallback((state: ConfirmState) => {
    setConfirm(state);
  }, []);

  const handleConfirm = useCallback(async () => {
    if (!confirm) return;
    setConfirmBusy(true);
    try {
      await confirm.onConfirm();
      setConfirm(null);
    } catch {
      /* erreur déjà affichée via run */
    } finally {
      setConfirmBusy(false);
    }
  }, [confirm]);

  const movePathsTo = async (paths: string[], destination: string) => {
    const filtered = paths.filter((p) => {
      if (p === destination) return false;
      if (destination.startsWith(`${p}/`)) return false;
      return true;
    });
    if (!filtered.length) return;
    await run(async () => {
      await apiRequest("/files/move/", {
        method: "POST",
        body: JSON.stringify({ paths: filtered, destination }),
      });
    });
  };

  async function openEditor(entry: FileEntry) {
    if (
      !entry.is_text &&
      !entry.name.match(
        /\.(txt|html?|css|js|json|md|py|php|env|conf|ini|yml|yaml|xml|sh|sql|log|csv)$/i,
      )
    ) {
      setError("Prévisualisation texte non disponible pour ce type.");
      return;
    }
    const data = await apiRequest<{ path: string; content: string }>(
      `/files/read/?path=${encodeURIComponent(entry.path)}`,
    );
    setEditor({ path: data.path, content: data.content, original: data.content });
  }

  function requestCloseEditor() {
    if (!editor) return;
    if (editor.content === editor.original) {
      setEditor(null);
      return;
    }
    askConfirm({
      title: "Modifications non enregistrées",
      message: `Le fichier « ${editor.path} » a été modifié. Fermer sans enregistrer ?`,
      confirmLabel: "Fermer sans enregistrer",
      danger: true,
      onConfirm: () => {
        setEditor(null);
      },
    });
  }

  function requestSaveEditor() {
    if (!editor) return;
    askConfirm({
      title: "Enregistrer le fichier",
      message: `Confirmer l'enregistrement de « ${editor.path} » ?`,
      confirmLabel: "Enregistrer",
      onConfirm: async () => {
        await run(async () => {
          await apiRequest("/files/write/", {
            method: "PUT",
            body: JSON.stringify({ path: editor.path, content: editor.content }),
          });
          setEditor(null);
        });
      },
    });
  }

  function requestDelete() {
    if (!selected.length) return;
    const names = selected.map((p) => p.split("/").pop() || p);
    const preview =
      names.length <= 5
        ? names.map((n) => `• ${n}`).join("\n")
        : `${names
            .slice(0, 5)
            .map((n) => `• ${n}`)
            .join("\n")}\n… et ${names.length - 5} autre(s)`;
    askConfirm({
      title: "Supprimer",
      message: `Supprimer définitivement ${selected.length} élément(s) ?\n\n${preview}`,
      confirmLabel: "Supprimer",
      danger: true,
      onConfirm: async () => {
        await run(() =>
          apiRequest("/files/delete/", {
            method: "POST",
            body: JSON.stringify({ paths: selected }),
          }),
        );
      },
    });
  }

  function requestRename() {
    if (selected.length !== 1) return;
    const current = selected[0].split("/").pop() || selected[0];
    setRenameValue(current);
    setRenameOpen(true);
  }

  function confirmRename() {
    const name = renameValue.trim();
    if (!name || selected.length !== 1) return;
    const from = selected[0].split("/").pop() || selected[0];
    setRenameOpen(false);
    askConfirm({
      title: "Renommer",
      message: `Renommer « ${from} » en « ${name} » ?`,
      confirmLabel: "Renommer",
      onConfirm: async () => {
        await run(() =>
          apiRequest("/files/rename/", {
            method: "POST",
            body: JSON.stringify({ path: selected[0], new_name: name }),
          }),
        );
      },
    });
  }

  function requestChmodApply() {
    if (!chmodPath) return;
    askConfirm({
      title: "Modifier les permissions",
      message: `Appliquer le mode ${chmodMode} à « ${chmodPath} » ?`,
      confirmLabel: "Appliquer",
      onConfirm: async () => {
        await run(async () => {
          await apiRequest("/files/chmod/", {
            method: "POST",
            body: JSON.stringify({ path: chmodPath, mode: chmodMode }),
          });
          setChmodPath(null);
        });
      },
    });
  }

  function toggleSelect(path: string, e: { ctrlKey: boolean; metaKey: boolean; shiftKey: boolean }) {
    const multi = e.ctrlKey || e.metaKey;
    const paths = entryPaths;
    const idx = paths.indexOf(path);

    if (e.shiftKey && lastClickedRef.current) {
      const start = paths.indexOf(lastClickedRef.current);
      if (start >= 0 && idx >= 0) {
        const lo = Math.min(start, idx);
        const hi = Math.max(start, idx);
        const range = paths.slice(lo, hi + 1);
        setSelected((prev) =>
          multi ? Array.from(new Set([...prev, ...range])) : range,
        );
        return;
      }
    }

    lastClickedRef.current = path;
    setSelected((prev) => {
      if (multi) {
        return prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path];
      }
      return prev.includes(path) && prev.length === 1 ? [] : [path];
    });
  }

  function toggleCheckbox(path: string) {
    lastClickedRef.current = path;
    setSelected((prev) =>
      prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path],
    );
  }

  function toggleSelectAll() {
    if (allSelected) {
      setSelected((prev) => prev.filter((p) => !entryPaths.includes(p)));
      return;
    }
    setSelected((prev) => Array.from(new Set([...prev, ...entryPaths])));
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
    <div className="space-y-2 animate-fade-up">
      <div className="vz-panel flex flex-wrap items-center justify-between gap-2 px-3 py-2">
        <div>
          <h1 className="text-base font-semibold leading-tight">{title}</h1>
          <p className="text-[11px] text-cp-muted">
            Glisser-déposer · édition · jailé dans le home
          </p>
        </div>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={() => void refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={`h-3 w-3 ${isFetching ? "animate-spin" : ""}`} />
          Actualiser
        </button>
      </div>

      <div className="vz-panel flex flex-wrap items-center gap-0.5 px-2 py-1 text-xs">
        {crumbs.map((c, idx) => (
          <span key={c.path || "root"} className="inline-flex items-center gap-0.5">
            {idx > 0 && <ChevronRight className="h-3 w-3 text-cp-muted" />}
            <button
              type="button"
              className="rounded px-1 py-0.5 hover:bg-cp-orange-soft hover:text-cp-orange-dark"
              onClick={() => setCwd(c.path)}
            >
              {c.label}
            </button>
          </span>
        ))}
      </div>

      <div className="vz-panel flex flex-wrap items-center gap-1 px-2 py-1.5">
        <button
          type="button"
          className="vz-btn-primary vz-btn-sm"
          onClick={() => launchUpload(cwd)}
          title="Ouvre un nouvel onglet pour suivre l'upload"
        >
          <Upload className="h-3 w-3" />
          Upload
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={() => launchUpload(cwd, { preferFolder: true })}
          title="Ouvre un nouvel onglet pour envoyer un dossier"
        >
          <FolderPlus className="h-3 w-3" />
          Dossier
        </button>
        {selected.length > 0 && (
          <span className="ml-1 mr-1 text-[11px] font-medium text-cp-muted">
            {selected.length} sélectionné{selected.length > 1 ? "s" : ""}
          </span>
        )}
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={!selected.length}
          onClick={() => setClipboard({ mode: "copy", paths: selected })}
        >
          <Copy className="h-3 w-3" />
          Copier
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={!selected.length}
          onClick={() => setClipboard({ mode: "cut", paths: selected })}
        >
          <Scissors className="h-3 w-3" />
          Couper
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
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
          <ClipboardPaste className="h-3 w-3" />
          Coller
        </button>
        <button type="button" className="vz-btn-ghost vz-btn-sm" disabled={!selected.length} onClick={requestDelete}>
          <Trash2 className="h-3 w-3" />
          Supprimer
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
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
          <Archive className="h-3 w-3" />
          Zip
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={!selected.length}
          onClick={() => void downloadSelected()}
        >
          <Download className="h-3 w-3" />
          Télécharger
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={selected.length !== 1}
          onClick={() => {
            const path = selected[0];
            setChmodPath(path);
            const entry = data?.entries.find((e) => e.path === path);
            if (entry) setChmodMode(entry.mode.toString(8).padStart(3, "0"));
          }}
        >
          <Shield className="h-3 w-3" />
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
            className="vz-input !px-2 !py-1 !text-xs w-36"
            placeholder="Rechercher…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="vz-btn-ghost vz-btn-sm" type="submit">
            <Search className="h-3 w-3" />
          </button>
        </form>
      </div>

      <div className="grid gap-2 lg:grid-cols-[1fr_180px]">
        <div
          className={`vz-panel relative min-h-[360px] overflow-auto ${
            dragOver && !internalDrag ? "ring-2 ring-cp-orange" : ""
          }`}
          onDragEnter={(e) => {
            e.preventDefault();
            dragDepth.current += 1;
            if (e.dataTransfer.types.includes("Files")) {
              setInternalDrag(false);
              setDragOver(true);
            }
          }}
          onDragOver={(e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = internalDrag ? "move" : "copy";
          }}
          onDragLeave={() => {
            dragDepth.current = Math.max(0, dragDepth.current - 1);
            if (dragDepth.current === 0) {
              setDragOver(false);
              setDropTargetPath(null);
            }
          }}
          onDrop={(e) => {
            e.preventDefault();
            dragDepth.current = 0;
            setDragOver(false);
            setDropTargetPath(null);
            const internal = e.dataTransfer.getData("application/x-vzone-paths");
            if (internal) {
              try {
                const paths = JSON.parse(internal) as string[];
                void movePathsTo(paths, cwd);
              } catch {
                /* ignore */
              }
              setInternalDrag(false);
              return;
            }
            void launchUploadJobs(cwd, () => collectDataTransferJobs(e.dataTransfer));
          }}
        >
          <table className="min-w-full text-left text-xs">
            <thead className="sticky top-0 bg-cp-canvas text-[10px] uppercase tracking-wide text-cp-muted dark:bg-ink-900">
              <tr>
                <th className="w-8 px-1.5 py-1.5">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-cp-orange"
                    checked={allSelected}
                    ref={(el) => {
                      if (el) el.indeterminate = someSelected && !allSelected;
                    }}
                    onChange={toggleSelectAll}
                    title="Tout sélectionner"
                    aria-label="Tout sélectionner"
                  />
                </th>
                <th className="px-2 py-1.5 font-semibold">Nom</th>
                <th className="w-20 px-2 py-1.5 font-semibold">Taille</th>
                <th className="w-24 px-2 py-1.5 font-semibold">Perms</th>
                <th className="w-36 px-2 py-1.5 font-semibold">Modifié</th>
              </tr>
            </thead>
            <tbody>
              {cwd && (
                <tr
                  className={`cursor-pointer border-t border-cp-border/80 hover:bg-cp-orange-soft/40 dark:border-ink-800 ${
                    dropTargetPath === ".." ? "bg-cp-orange-soft/70 ring-1 ring-inset ring-cp-orange" : ""
                  }`}
                  onDoubleClick={() => {
                    const parent = cwd.split("/").slice(0, -1).join("/");
                    setCwd(parent);
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setDropTargetPath("..");
                  }}
                  onDragLeave={() => setDropTargetPath((p) => (p === ".." ? null : p))}
                  onDrop={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setDropTargetPath(null);
                    const parent = cwd.split("/").slice(0, -1).join("/");
                    const internal = e.dataTransfer.getData("application/x-vzone-paths");
                    if (internal) {
                      try {
                        void movePathsTo(JSON.parse(internal) as string[], parent);
                      } catch {
                        /* ignore */
                      }
                      return;
                    }
                    void launchUploadJobs(parent, () => collectDataTransferJobs(e.dataTransfer));
                  }}
                >
                  <td className="px-2 py-1 font-medium" colSpan={5}>
                    ..
                  </td>
                </tr>
              )}
              {isLoading && !data && (
                <tr>
                  <td className="px-2 py-3 text-cp-muted" colSpan={5}>
                    Chargement…
                  </td>
                </tr>
              )}
              {(data?.entries ?? []).map((entry) => {
                const active = selected.includes(entry.path);
                const isDropTarget = dropTargetPath === entry.path && entry.is_dir;
                return (
                  <tr
                    key={entry.path}
                    draggable
                    className={`cursor-pointer border-t border-cp-border/70 dark:border-ink-800 ${
                      isDropTarget
                        ? "bg-cp-orange-soft/80 ring-1 ring-inset ring-cp-orange"
                        : active
                          ? "bg-cp-orange-soft/60"
                          : "hover:bg-cp-canvas dark:hover:bg-ink-900"
                    }`}
                    onClick={(e) => toggleSelect(entry.path, e)}
                    onDoubleClick={() => {
                      if (entry.is_dir) {
                        setCwd(entry.path);
                        setSelected([]);
                      } else {
                        void openEditor(entry);
                      }
                    }}
                    onDragStart={(e) => {
                      setInternalDrag(true);
                      const paths =
                        selected.includes(entry.path) && selected.length > 0
                          ? selected
                          : [entry.path];
                      e.dataTransfer.setData(
                        "application/x-vzone-paths",
                        JSON.stringify(paths),
                      );
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    onDragEnd={() => {
                      setInternalDrag(false);
                      setDropTargetPath(null);
                      setDragOver(false);
                      dragDepth.current = 0;
                    }}
                    onDragOver={(e) => {
                      if (!entry.is_dir) return;
                      e.preventDefault();
                      e.stopPropagation();
                      setDropTargetPath(entry.path);
                    }}
                    onDragLeave={() =>
                      setDropTargetPath((p) => (p === entry.path ? null : p))
                    }
                    onDrop={(e) => {
                      if (!entry.is_dir) return;
                      e.preventDefault();
                      e.stopPropagation();
                      setDropTargetPath(null);
                      setDragOver(false);
                      dragDepth.current = 0;
                      const internal = e.dataTransfer.getData("application/x-vzone-paths");
                      if (internal) {
                        try {
                          void movePathsTo(JSON.parse(internal) as string[], entry.path);
                        } catch {
                          /* ignore */
                        }
                        setInternalDrag(false);
                        return;
                      }
                      void launchUploadJobs(entry.path, () =>
                        collectDataTransferJobs(e.dataTransfer),
                      );
                    }}
                  >
                    <td
                      className="px-1.5 py-1"
                      onClick={(e) => e.stopPropagation()}
                      onDoubleClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 accent-cp-orange"
                        checked={active}
                        onChange={() => toggleCheckbox(entry.path)}
                        aria-label={`Sélectionner ${entry.name}`}
                      />
                    </td>
                    <td className="max-w-[1px] truncate px-2 py-1">
                      <span className="inline-flex min-w-0 items-center gap-1.5">
                        {entry.is_dir ? (
                          <Folder className="h-3.5 w-3.5 shrink-0 text-cp-orange" />
                        ) : (
                          <FileText className="h-3.5 w-3.5 shrink-0 text-cp-link" />
                        )}
                        <span className="truncate font-medium">{entry.name}</span>
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-2 py-1 text-cp-muted">
                      {entry.is_dir ? "—" : formatBytes(entry.size)}
                    </td>
                    <td className="whitespace-nowrap px-2 py-1 font-mono text-[10px] text-cp-muted">
                      {entry.permissions}
                    </td>
                    <td className="whitespace-nowrap px-2 py-1 text-[10px] text-cp-muted">
                      {new Date(entry.modified_at).toLocaleString("fr-FR", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {dragOver && !internalDrag && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-cp-orange/15 text-sm font-semibold text-cp-orange-dark">
              Déposez fichiers ou dossiers ici
            </div>
          )}
          {!isLoading && !(data?.entries?.length) && !cwd && (
            <p className="px-3 py-4 text-center text-[11px] text-cp-muted">
              Glissez-déposez des fichiers ou dossiers (nouvel onglet), ou utilisez Upload / Dossier.
            </p>
          )}
        </div>

        <div className="space-y-2">
          <form className="vz-panel space-y-1.5 p-2" onSubmit={onCreateFolder}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-cp-muted">Nouveau dossier</p>
            <input className="vz-input !px-2 !py-1 !text-xs" name="name" placeholder="nom" required />
            <button className="vz-btn-ghost vz-btn-sm w-full" type="submit">
              <FolderPlus className="h-3 w-3" />
              Créer
            </button>
          </form>
          <form className="vz-panel space-y-1.5 p-2" onSubmit={onCreateFile}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-cp-muted">Nouveau fichier</p>
            <input className="vz-input !px-2 !py-1 !text-xs" name="name" placeholder="index.html" required />
            <button className="vz-btn-ghost vz-btn-sm w-full" type="submit">
              <FilePlus2 className="h-3 w-3" />
              Créer
            </button>
          </form>
          {selected.length === 1 && (
            <div className="vz-panel space-y-1 p-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-cp-muted">Actions</p>
              <button
                type="button"
                className="vz-btn-ghost vz-btn-sm w-full"
                onClick={() => {
                  const entry = data?.entries.find((e) => e.path === selected[0]);
                  if (entry && !entry.is_dir) void openEditor(entry);
                }}
              >
                <Pencil className="h-3 w-3" />
                Éditer
              </button>
              <button
                type="button"
                className="vz-btn-ghost vz-btn-sm w-full"
                onClick={() => {
                  const entry = data?.entries.find((e) => e.path === selected[0]);
                  if (!entry) return;
                  if (entry.name.match(/\.(zip|tar\.gz|tgz|tar)$/i)) {
                    askConfirm({
                      title: "Décompresser",
                      message: `Décompresser « ${entry.name} » dans le dossier courant ?`,
                      confirmLabel: "Décompresser",
                      onConfirm: async () => {
                        await run(() =>
                          apiRequest("/files/decompress/", {
                            method: "POST",
                            body: JSON.stringify({ archive: entry.path, destination: cwd }),
                          }),
                        );
                      },
                    });
                  }
                }}
              >
                <Archive className="h-3 w-3" />
                Décompresser
              </button>
              <button type="button" className="vz-btn-ghost vz-btn-sm w-full" onClick={requestRename}>
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
              <p className="font-semibold">
                {editor.path}
                {editor.content !== editor.original ? (
                  <span className="ml-2 text-xs font-normal text-cp-muted">(modifié)</span>
                ) : null}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="vz-btn-primary"
                  disabled={editor.content === editor.original}
                  onClick={requestSaveEditor}
                >
                  Enregistrer
                </button>
                <button type="button" className="vz-btn-ghost" onClick={requestCloseEditor}>
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
              <button type="button" className="vz-btn-primary" onClick={requestChmodApply}>
                Appliquer
              </button>
            </div>
          </div>
        </div>
      )}

      {renameOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950">
            <p className="mb-3 font-semibold">Renommer</p>
            <input
              className="vz-input mb-3"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") confirmRename();
              }}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setRenameOpen(false)}>
                Annuler
              </button>
              <button
                type="button"
                className="vz-btn-primary"
                disabled={!renameValue.trim()}
                onClick={confirmRename}
              >
                Continuer
              </button>
            </div>
          </div>
        </div>
      )}

      {confirm && (
        <ConfirmDialog
          state={{ ...confirm, onConfirm: handleConfirm }}
          busy={confirmBusy}
          onCancel={() => {
            if (!confirmBusy) setConfirm(null);
          }}
        />
      )}
    </div>
  );
}
