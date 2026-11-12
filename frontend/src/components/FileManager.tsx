import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ChevronRight,
  ClipboardPaste,
  Copy,
  Download,
  Eye,
  EyeOff,
  FilePlus2,
  FolderPlus,
  PanelLeftClose,
  PanelLeft,
  RefreshCw,
  Scissors,
  Search,
  Shield,
  Trash2,
  Upload,
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
import { openEditTab } from "@/lib/fileEditor";
import { ContextMenu } from "@/components/file-manager/ContextMenu";
import { DirectoryTree } from "@/components/file-manager/DirectoryTree";
import {
  FileTypeIcon,
  isArchiveEntry,
  isEditableEntry,
  isImageEntry,
} from "@/components/file-manager/fileIcons";
import { PreviewModal } from "@/components/file-manager/PreviewModal";
import type {
  ClipMode,
  ConfirmState,
  ContextMenuState,
  FileEntry,
  Listing,
  SortDir,
  SortKey,
} from "@/components/file-manager/types";

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
        <p className="mt-2 whitespace-pre-wrap text-sm text-cp-muted">{state.message}</p>
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

function sortEntries(entries: FileEntry[], key: SortKey, dir: SortDir) {
  const mul = dir === "asc" ? 1 : -1;
  return [...entries].sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
    let cmp = 0;
    if (key === "name") cmp = a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    else if (key === "size") cmp = a.size - b.size;
    else if (key === "modified")
      cmp = new Date(a.modified_at).getTime() - new Date(b.modified_at).getTime();
    else cmp = a.permissions.localeCompare(b.permissions);
    return cmp * mul;
  });
}

export function FileManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const location = useLocation();
  const panelBase = resolvePanelBase(location.pathname);
  const token = useAuthStore((s) => s.accessToken);
  const [cwd, setCwd] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [clipboard, setClipboard] = useState<{ mode: ClipMode; paths: string[] }>({
    mode: null,
    paths: [],
  });
  const [query, setQuery] = useState("");
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
  const [showHidden, setShowHidden] = useState(false);
  const [showTree, setShowTree] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [previewEntry, setPreviewEntry] = useState<FileEntry | null>(null);
  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [createFileOpen, setCreateFileOpen] = useState(false);
  const dragDepth = useRef(0);
  const lastClickedRef = useRef<string | null>(null);

  const accessToken = useAuthStore((s) => s.accessToken);
  const authHydrated = useAuthStore((s) => s._hasHydrated);
  const tokenReady = Boolean(accessToken && authHydrated);
  const standalone = location.pathname.includes("/fm");

  const { data, isLoading, isFetching, isError, error: queryError, refetch } = useQuery({
    queryKey: ["files", cwd],
    queryFn: () => apiRequest<Listing>(`/files/?path=${encodeURIComponent(cwd)}`),
    enabled: tokenReady,
    placeholderData: (prev) => prev,
    staleTime: 15_000,
    retry: 2,
  });

  const listError =
    error ||
    (isError
      ? queryError instanceof Error
        ? queryError.message
        : "Impossible de charger le dossier."
      : null);

  const visibleEntries = useMemo(() => {
    const raw = data?.entries ?? [];
    const filtered = showHidden ? raw : raw.filter((e) => !e.name.startsWith("."));
    return sortEntries(filtered, sortKey, sortDir);
  }, [data?.entries, showHidden, sortKey, sortDir]);

  const entryPaths = useMemo(() => visibleEntries.map((e) => e.path), [visibleEntries]);
  const allSelected =
    entryPaths.length > 0 && entryPaths.every((p) => selected.includes(p));
  const someSelected = selected.some((p) => entryPaths.includes(p));
  const selectedEntries = useMemo(
    () => visibleEntries.filter((e) => selected.includes(e.path)),
    [visibleEntries, selected],
  );

  useEffect(() => {
    setSelected([]);
    lastClickedRef.current = null;
    setContextMenu(null);
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

  const askConfirm = useCallback((state: ConfirmState) => setConfirm(state), []);

  const handleConfirm = useCallback(async () => {
    if (!confirm) return;
    setConfirmBusy(true);
    try {
      await confirm.onConfirm();
      setConfirm(null);
    } catch {
      /* déjà affiché */
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

  function launchEditor(entry: FileEntry) {
    if (!isEditableEntry(entry)) {
      setError("Édition texte non disponible pour ce type de fichier.");
      return;
    }
    const win = openEditTab(panelBase, entry.path);
    if (!win) {
      setError(
        "Impossible d'ouvrir l'onglet d'édition. Autorisez les pop-ups pour ce site, puis réessayez.",
      );
    }
  }

  function requestDelete(paths = selected) {
    if (!paths.length) return;
    const names = paths.map((p) => p.split("/").pop() || p);
    const preview =
      names.length <= 5
        ? names.map((n) => `• ${n}`).join("\n")
        : `${names
            .slice(0, 5)
            .map((n) => `• ${n}`)
            .join("\n")}\n… et ${names.length - 5} autre(s)`;
    askConfirm({
      title: "Supprimer",
      message: `Supprimer définitivement ${paths.length} élément(s) ?\n\n${preview}`,
      confirmLabel: "Supprimer",
      danger: true,
      onConfirm: async () => {
        await run(() =>
          apiRequest("/files/delete/", {
            method: "POST",
            body: JSON.stringify({ paths }),
          }),
        );
      },
    });
  }

  function requestRename(path = selected[0]) {
    if (!path) return;
    setSelected([path]);
    setRenameValue(path.split("/").pop() || path);
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
        setSelected((prev) => (multi ? Array.from(new Set([...prev, ...range])) : range));
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

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  async function downloadSelected(paths = selected) {
    const files = (data?.entries ?? []).filter((e) => paths.includes(e.path) && !e.is_dir);
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
    setCreateFolderOpen(false);
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
    setCreateFileOpen(false);
  }

  function openEntry(entry: FileEntry) {
    if (entry.is_dir) {
      setCwd(entry.path);
      setSelected([]);
      return;
    }
    if (isImageEntry(entry)) {
      setPreviewEntry(entry);
      return;
    }
    if (isEditableEntry(entry)) launchEditor(entry);
    else void downloadSelected([entry.path]);
  }

  useEffect(() => {
    if (!standalone) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "Delete" || e.key === "Backspace") {
        if (selected.length) {
          e.preventDefault();
          requestDelete();
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
        e.preventDefault();
        setSelected(entryPaths);
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c") {
        if (selected.length) setClipboard({ mode: "copy", paths: selected });
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "x") {
        if (selected.length) setClipboard({ mode: "cut", paths: selected });
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "v") {
        if (clipboard.mode && clipboard.paths.length) {
          void run(async () => {
            const endpoint = clipboard.mode === "cut" ? "/files/move/" : "/files/copy/";
            await apiRequest(endpoint, {
              method: "POST",
              body: JSON.stringify({ paths: clipboard.paths, destination: cwd }),
            });
            setClipboard({ mode: null, paths: [] });
          });
        }
      } else if (e.key === "F2" && selected.length === 1) {
        e.preventDefault();
        requestRename();
      } else if (e.key === "Enter" && selected.length === 1) {
        const entry = visibleEntries.find((x) => x.path === selected[0]);
        if (entry) openEntry(entry);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [standalone, selected, clipboard, cwd, entryPaths, visibleEntries]);

  const contextEntry =
    contextMenu &&
    (data?.entries.find((e) => e.path === contextMenu.path) ||
      visibleEntries.find((e) => e.path === contextMenu.path));

  const totalBytes = visibleEntries.reduce((acc, e) => acc + (e.is_dir ? 0 : e.size), 0);

  return (
    <div
      className={`animate-fade-up ${
        standalone ? "flex h-full min-h-0 flex-col gap-1.5" : "space-y-2"
      }`}
    >
      <div className="vz-panel flex shrink-0 flex-wrap items-center justify-between gap-2 px-3 py-2">
        <div className="min-w-0">
          <h1 className="text-base font-semibold leading-tight">{title}</h1>
          <p className="truncate text-[11px] text-cp-muted">
            {data?.root ? (
              <>
                Racine : <span className="font-mono text-cp-text">{data.root}</span>
              </>
            ) : (
              "Parcourir, éditer et organiser comme sur cPanel"
            )}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="vz-btn-ghost vz-btn-sm"
            onClick={() => setShowTree((v) => !v)}
            title={showTree ? "Masquer l'arbre" : "Afficher l'arbre"}
          >
            {showTree ? <PanelLeftClose className="h-3.5 w-3.5" /> : <PanelLeft className="h-3.5 w-3.5" />}
          </button>
          <button
            type="button"
            className="vz-btn-ghost vz-btn-sm"
            onClick={() => setShowHidden((v) => !v)}
            title={showHidden ? "Masquer les fichiers cachés" : "Afficher les fichiers cachés"}
          >
            {showHidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            <span className="vz-label-sm">{showHidden ? "Masquer ." : "Afficher ."}</span>
          </button>
          <button
            type="button"
            className="vz-btn-ghost vz-btn-sm"
            onClick={() => void refetch()}
            disabled={isFetching || !tokenReady}
          >
            <RefreshCw className={`h-3 w-3 ${isFetching ? "animate-spin" : ""}`} />
            Actualiser
          </button>
        </div>
      </div>

      {listError ? (
        <div className="rounded-xl border border-cp-danger/40 bg-cp-danger/10 px-3 py-2 text-sm text-cp-danger">
          {listError}
          <button
            type="button"
            className="ml-3 underline"
            onClick={() => {
              setError(null);
              void refetch();
            }}
          >
            Réessayer
          </button>
        </div>
      ) : null}

      <div className="vz-panel flex shrink-0 flex-wrap items-center gap-0.5 px-2 py-1 text-xs">
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

      <div className="vz-panel flex shrink-0 flex-wrap items-center gap-1 px-2 py-1.5">
        <button type="button" className="vz-btn-primary vz-btn-sm" onClick={() => launchUpload(cwd)}>
          <Upload className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Upload</span>
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={() => launchUpload(cwd, { preferFolder: true })}
        >
          <FolderPlus className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Dossier</span>
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={() => setCreateFolderOpen(true)}
        >
          <FolderPlus className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Nouveau</span>
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={() => setCreateFileOpen(true)}
        >
          <FilePlus2 className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Fichier</span>
        </button>
        <span className="mx-0.5 h-4 w-px bg-cp-border" />
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={!selected.length}
          onClick={() => setClipboard({ mode: "copy", paths: selected })}
        >
          <Copy className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Copier</span>
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={!selected.length}
          onClick={() => setClipboard({ mode: "cut", paths: selected })}
        >
          <Scissors className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Couper</span>
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
          <ClipboardPaste className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Coller</span>
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={!selected.length}
          onClick={() => requestDelete()}
        >
          <Trash2 className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Supprimer</span>
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
          <Archive className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Zip</span>
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={!selectedEntries.some((e) => !e.is_dir)}
          onClick={() => void downloadSelected()}
        >
          <Download className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Télécharger</span>
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={selected.length !== 1}
          onClick={() => {
            if (selected[0]) {
              setChmodPath(selected[0]);
              setChmodMode("644");
            }
          }}
        >
          <Shield className="h-3.5 w-3.5" />
          <span className="vz-label-sm">chmod</span>
        </button>
        <form
          className="ml-auto flex min-w-[140px] flex-1 gap-1 sm:max-w-[16rem]"
          onSubmit={(e) => {
            e.preventDefault();
            searchMutation.mutate();
          }}
        >
          <input
            className="vz-input !px-2 !py-1 !text-xs w-full"
            placeholder="Rechercher…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="vz-btn-ghost vz-btn-sm shrink-0" type="submit" title="Rechercher">
            <Search className="h-3.5 w-3.5" />
          </button>
        </form>
      </div>

      <div
        className={`grid min-h-0 overflow-hidden rounded-lg border border-cp-border bg-white dark:border-ink-800 dark:bg-ink-950 ${
          standalone ? "flex-1" : "min-h-[360px]"
        } ${showTree ? "grid-cols-1 md:grid-cols-[200px_minmax(0,1fr)]" : "grid-cols-1"}`}
      >
        {showTree && (
          <div className="hidden min-h-0 md:block">
            <DirectoryTree cwd={cwd} onNavigate={setCwd} enabled={tokenReady} />
          </div>
        )}

        <div
          className={`relative min-h-0 overflow-auto ${
            dragOver && !internalDrag ? "ring-2 ring-inset ring-cp-orange" : ""
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
                void movePathsTo(JSON.parse(internal) as string[], cwd);
              } catch {
                /* ignore */
              }
              setInternalDrag(false);
              return;
            }
            void launchUploadJobs(cwd, () => collectDataTransferJobs(e.dataTransfer));
          }}
          onClick={() => setContextMenu(null)}
        >
          <table className="min-w-full text-left text-xs">
            <thead className="sticky top-0 z-10 bg-[#eef3f8] text-[10px] uppercase tracking-wide text-cp-muted dark:bg-ink-900">
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
                    aria-label="Tout sélectionner"
                  />
                </th>
                <th className="cursor-pointer px-2 py-1.5 font-semibold" onClick={() => toggleSort("name")}>
                  Nom {sortKey === "name" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
                <th
                  className="hidden w-20 cursor-pointer px-2 py-1.5 font-semibold sm:table-cell"
                  onClick={() => toggleSort("size")}
                >
                  Taille {sortKey === "size" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
                <th
                  className="hidden w-24 cursor-pointer px-2 py-1.5 font-semibold md:table-cell"
                  onClick={() => toggleSort("perms")}
                >
                  Perms {sortKey === "perms" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
                <th
                  className="hidden w-36 cursor-pointer px-2 py-1.5 font-semibold md:table-cell"
                  onClick={() => toggleSort("modified")}
                >
                  Modifié {sortKey === "modified" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
              </tr>
            </thead>
            <tbody>
              {cwd && (
                <tr
                  className={`cursor-pointer border-t border-cp-border/80 hover:bg-cp-orange-soft/40 dark:border-ink-800 ${
                    dropTargetPath === ".." ? "bg-cp-orange-soft/70 ring-1 ring-inset ring-cp-orange" : ""
                  }`}
                  onDoubleClick={() => setCwd(cwd.split("/").slice(0, -1).join("/"))}
                  onDragOver={(e) => {
                    e.preventDefault();
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
                    }
                  }}
                >
                  <td className="px-1.5 py-1" />
                  <td className="px-2 py-1.5 font-medium text-cp-muted" colSpan={4}>
                    ..
                  </td>
                </tr>
              )}

              {tokenReady && isLoading && !data && (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-cp-muted">
                    Chargement du dossier…
                  </td>
                </tr>
              )}

              {visibleEntries.map((entry) => {
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
                    onDoubleClick={() => openEntry(entry)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      if (!selected.includes(entry.path)) setSelected([entry.path]);
                      setContextMenu({ x: e.clientX, y: e.clientY, path: entry.path });
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
                    <td className="max-w-[1px] truncate px-2 py-1.5">
                      <span className="inline-flex min-w-0 items-center gap-1.5">
                        <FileTypeIcon entry={entry} />
                        <span className="truncate font-medium">{entry.name}</span>
                      </span>
                    </td>
                    <td className="hidden whitespace-nowrap px-2 py-1 text-cp-muted sm:table-cell">
                      {entry.is_dir ? "—" : formatBytes(entry.size)}
                    </td>
                    <td className="hidden whitespace-nowrap px-2 py-1 font-mono text-[10px] text-cp-muted md:table-cell">
                      {entry.permissions}
                    </td>
                    <td className="hidden whitespace-nowrap px-2 py-1 text-[10px] text-cp-muted md:table-cell">
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
          {tokenReady && !isLoading && !isError && data && visibleEntries.length === 0 && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 px-4 text-center">
              <FolderPlus className="h-10 w-10 text-cp-orange/50" />
              <p className="text-sm font-medium text-cp-text">Dossier vide</p>
              <p className="max-w-sm text-[12px] text-cp-muted">
                Glissez-déposez des fichiers ici, ou utilisez Upload / Nouveau.
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 rounded-md border border-cp-border bg-[#f3f6fa] px-2 py-1 text-[10px] text-cp-muted dark:border-ink-800 dark:bg-ink-950">
        <span>
          {visibleEntries.length} élément(s)
          {selected.length ? ` · ${selected.length} sélectionné(s)` : ""}
          {clipboard.mode ? ` · presse-papiers (${clipboard.mode})` : ""}
        </span>
        <span>
          Fichiers : {formatBytes(totalBytes)}
          {standalone ? " · Raccourcis : Del · F2 · Ctrl+A/C/X/V" : ""}
        </span>
      </div>

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

      {createFolderOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <form
            className="w-full max-w-sm space-y-3 rounded border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950"
            onSubmit={onCreateFolder}
          >
            <p className="font-semibold">Nouveau dossier</p>
            <input className="vz-input" name="name" placeholder="nom" required autoFocus />
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setCreateFolderOpen(false)}>
                Annuler
              </button>
              <button className="vz-btn-primary" type="submit">
                Créer
              </button>
            </div>
          </form>
        </div>
      )}

      {createFileOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <form
            className="w-full max-w-sm space-y-3 rounded border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950"
            onSubmit={onCreateFile}
          >
            <p className="font-semibold">Nouveau fichier</p>
            <input className="vz-input" name="name" placeholder="index.html" required autoFocus />
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setCreateFileOpen(false)}>
                Annuler
              </button>
              <button className="vz-btn-primary" type="submit">
                Créer
              </button>
            </div>
          </form>
        </div>
      )}

      {renameOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950">
            <p className="mb-3 font-semibold">Renommer</p>
            <input
              className="vz-input"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") confirmRename();
              }}
            />
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setRenameOpen(false)}>
                Annuler
              </button>
              <button type="button" className="vz-btn-primary" onClick={confirmRename}>
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {chmodPath && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950">
            <p className="mb-3 font-semibold">Permissions — {chmodPath}</p>
            <input
              className="vz-input font-mono"
              value={chmodMode}
              onChange={(e) => setChmodMode(e.target.value)}
              placeholder="644"
            />
            <div className="mt-3 flex justify-end gap-2">
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

      {confirm && (
        <ConfirmDialog
          state={{ ...confirm, onConfirm: handleConfirm }}
          busy={confirmBusy}
          onCancel={() => !confirmBusy && setConfirm(null)}
        />
      )}

      {previewEntry && (
        <PreviewModal
          entry={previewEntry}
          token={token}
          onClose={() => setPreviewEntry(null)}
          onDownload={() => void downloadSelected([previewEntry.path])}
        />
      )}

      {contextMenu && contextEntry && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          entry={contextEntry}
          onClose={() => setContextMenu(null)}
          onAction={(action) => {
            const entry = contextEntry;
            if (action === "open") openEntry(entry);
            else if (action === "edit") launchEditor(entry);
            else if (action === "preview") setPreviewEntry(entry);
            else if (action === "download") void downloadSelected([entry.path]);
            else if (action === "copy") setClipboard({ mode: "copy", paths: [entry.path] });
            else if (action === "cut") setClipboard({ mode: "cut", paths: [entry.path] });
            else if (action === "rename") requestRename(entry.path);
            else if (action === "chmod") {
              setChmodPath(entry.path);
              setChmodMode(entry.is_dir ? "755" : "644");
            } else if (action === "extract" && isArchiveEntry(entry)) {
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
            } else if (action === "delete") requestDelete([entry.path]);
          }}
        />
      )}
    </div>
  );
}
