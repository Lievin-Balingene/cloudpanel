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
  X,
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

type ConfirmState = {
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void | Promise<void>;
};

type UploadItem = {
  name: string;
  size: number;
  percent: number;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
};

const SIMPLE_UPLOAD_MAX = 1024 * 1024; // 1 Mo — au-delà / en secours : upload chunké binaire
const CHUNK_BYTES = 2 * 1024 * 1024; // 2 Mo (plus robuste derrière nginx/proxy)
const CHUNK_RETRIES = 5;

function parseUploadError(xhr: XMLHttpRequest, fallback: string): string {
  try {
    const payload = JSON.parse(xhr.responseText);
    if (payload?.error?.message) return String(payload.error.message);
  } catch {
    /* ignore */
  }
  if (xhr.status === 0) {
    return "Connexion interrompue pendant l'upload (réseau, proxy ou limite serveur). Réessayez.";
  }
  if (xhr.status === 401) return "Session expirée. Reconnectez-vous puis réessayez l'upload.";
  if (xhr.status === 413) return "Fichier trop volumineux pour le serveur (limite nginx/API).";
  if (xhr.status === 502 || xhr.status === 504) {
    return "Le serveur a coupé la connexion pendant l'upload. Réessayez.";
  }
  return `${fallback} (HTTP ${xhr.status})`;
}

function xhrSend(
  method: string,
  url: string,
  token: string | null,
  body: FormData | string | Blob,
  options?: {
    onProgress?: (loaded: number, total: number) => void;
    timeoutMs?: number;
    contentType?: string | null;
  },
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    xhr.timeout = options?.timeoutMs ?? 10 * 60 * 1000;
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    if (options?.contentType) {
      xhr.setRequestHeader("Content-Type", options.contentType);
    }

    xhr.upload.onprogress = (event) => {
      if (options?.onProgress && event.lengthComputable && event.total > 0) {
        options.onProgress(event.loaded, event.total);
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(xhr.responseText ? JSON.parse(xhr.responseText) : {});
        } catch {
          resolve({});
        }
        return;
      }
      reject(new ApiClientError(parseUploadError(xhr, "Upload échoué"), xhr.status));
    };

    xhr.onerror = () =>
      reject(
        new ApiClientError(
          "Connexion interrompue pendant l'upload (réseau, proxy ou limite serveur). Réessayez.",
          0,
        ),
      );
    xhr.ontimeout = () =>
      reject(new ApiClientError("Délai dépassé pendant l'upload. Réessayez.", 0));
    xhr.onabort = () => reject(new ApiClientError("Upload annulé.", 0));

    xhr.send(body);
  });
}

async function uploadSimple(
  file: File,
  cwd: string,
  token: string | null,
  onProgress: (percent: number) => void,
  relativePath?: string,
): Promise<void> {
  const body = new FormData();
  body.append("path", cwd);
  const rel = (relativePath || file.webkitRelativePath || file.name).replace(/\\/g, "/");
  body.append("relative_path", rel);
  body.append("file", file, file.name);
  await xhrSend("POST", "/api/v1/files/upload/", token, body, {
    timeoutMs: 15 * 60 * 1000,
    onProgress: (loaded, total) => {
      onProgress(Math.min(99, Math.round((loaded / total) * 100)));
    },
  });
  onProgress(100);
}

async function uploadChunkWithRetry(
  uploadId: string,
  index: number,
  blob: Blob,
  token: string | null,
  onChunkProgress: (ratio: number) => void,
): Promise<void> {
  let lastError: unknown;
  for (let attempt = 0; attempt < CHUNK_RETRIES; attempt++) {
    try {
      const url =
        `/api/v1/files/upload/chunk/?upload_id=${encodeURIComponent(uploadId)}` +
        `&index=${encodeURIComponent(String(index))}`;
      await xhrSend("POST", url, token, blob, {
        contentType: "application/octet-stream",
        timeoutMs: 10 * 60 * 1000,
        onProgress: (loaded, total) => onChunkProgress(total > 0 ? loaded / total : 0),
      });
      return;
    } catch (err) {
      lastError = err;
      // Ne pas retenter indéfiniment sur erreurs métier (4xx sauf timeout/réseau)
      if (err instanceof ApiClientError && err.status >= 400 && err.status < 500 && err.status !== 408) {
        throw err;
      }
      await new Promise((r) => setTimeout(r, 500 * (attempt + 1) ** 2));
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new ApiClientError("Échec envoi du chunk après plusieurs tentatives.", 0);
}

async function uploadChunked(
  file: File,
  cwd: string,
  token: string | null,
  onProgress: (percent: number) => void,
  relativePath?: string,
): Promise<void> {
  const rel = (relativePath || file.webkitRelativePath || file.name).replace(/\\/g, "/");
  const initRaw = await xhrSend(
    "POST",
    "/api/v1/files/upload/init/",
    token,
    JSON.stringify({
      path: cwd,
      name: rel,
      size: file.size,
      chunk_size: CHUNK_BYTES,
    }),
    { contentType: "application/json", timeoutMs: 60_000 },
  );
  const init = (initRaw as { data?: { upload_id: string; chunk_size: number; total_chunks: number } })
    ?.data;
  if (!init?.upload_id) {
    throw new ApiClientError("Réponse init upload invalide.", 0);
  }

  const chunkSize = init.chunk_size || CHUNK_BYTES;
  const totalChunks = init.total_chunks || Math.max(1, Math.ceil(file.size / chunkSize) || 1);

  try {
    for (let index = 0; index < totalChunks; index++) {
      const start = index * chunkSize;
      const end = Math.min(file.size, start + chunkSize);
      const blob = file.slice(start, end);
      await uploadChunkWithRetry(init.upload_id, index, blob, token, (ratio) => {
        const doneBytes = start + ratio * (end - start);
        const pct = file.size > 0 ? Math.min(99, Math.round((doneBytes / file.size) * 100)) : 99;
        onProgress(pct);
      });
      onProgress(
        file.size > 0 ? Math.min(99, Math.round(((index + 1) / totalChunks) * 100)) : 99,
      );
    }

    await xhrSend(
      "POST",
      "/api/v1/files/upload/complete/",
      token,
      JSON.stringify({ upload_id: init.upload_id }),
      { contentType: "application/json", timeoutMs: 15 * 60 * 1000 },
    );
    onProgress(100);
  } catch (err) {
    try {
      await xhrSend(
        "POST",
        "/api/v1/files/upload/abort/",
        token,
        JSON.stringify({ upload_id: init.upload_id }),
        { contentType: "application/json", timeoutMs: 30_000 },
      );
    } catch {
      /* ignore abort errors */
    }
    throw err;
  }
}

async function uploadWithProgress(
  file: File,
  cwd: string,
  token: string | null,
  onProgress: (percent: number) => void,
  relativePath?: string,
): Promise<void> {
  // Archives / gros fichiers : toujours chunké (évite coupure nginx sur un seul POST).
  const forceChunked =
    file.size > SIMPLE_UPLOAD_MAX || /\.(zip|tar|gz|tgz|rar|7z|iso|img|sql|bak)$/i.test(file.name);

  if (!forceChunked) {
    try {
      await uploadSimple(file, cwd, token, onProgress, relativePath);
      return;
    } catch (err) {
      if (!(err instanceof ApiClientError) || (err.status !== 0 && err.status !== 413 && err.status !== 502)) {
        throw err;
      }
    }
  }
  await uploadChunked(file, cwd, token, onProgress, relativePath);
}

/** Job d'upload : fichier ou dossier vide (mkdir). */
type DropJob =
  | { kind: "file"; file: File; relativePath: string }
  | { kind: "dir"; relativePath: string };

function readAllDirectoryEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    const all: FileSystemEntry[] = [];
    const readBatch = () => {
      reader.readEntries(
        (batch) => {
          if (!batch.length) {
            resolve(all);
            return;
          }
          all.push(...batch);
          readBatch();
        },
        (err) => reject(err),
      );
    };
    readBatch();
  });
}

function entryToFile(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => {
    entry.file(resolve, reject);
  });
}

async function walkFsEntry(entry: FileSystemEntry, prefix: string, out: DropJob[]): Promise<void> {
  if (entry.isFile) {
    const file = await entryToFile(entry as FileSystemFileEntry);
    const relativePath = prefix ? `${prefix}/${entry.name}` : entry.name;
    out.push({ kind: "file", file, relativePath });
    return;
  }
  if (entry.isDirectory) {
    const dir = entry as FileSystemDirectoryEntry;
    const nextPrefix = prefix ? `${prefix}/${entry.name}` : entry.name;
    const children = await readAllDirectoryEntries(dir.createReader());
    if (!children.length) {
      out.push({ kind: "dir", relativePath: nextPrefix });
      return;
    }
    for (const child of children) {
      await walkFsEntry(child, nextPrefix, out);
    }
  }
}

async function collectDataTransferJobs(dt: DataTransfer): Promise<DropJob[]> {
  const jobs: DropJob[] = [];
  const items = dt.items ? Array.from(dt.items) : [];
  const entries = items
    .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null))
    .filter((e): e is FileSystemEntry => Boolean(e));

  if (entries.length) {
    for (const entry of entries) {
      await walkFsEntry(entry, "", jobs);
    }
    return jobs;
  }

  // Fallback : fichiers plats (sans arborescence)
  for (const file of Array.from(dt.files || [])) {
    const rel = (file.webkitRelativePath || file.name).replace(/\\/g, "/");
    jobs.push({ kind: "file", file, relativePath: rel });
  }
  return jobs;
}

function collectFileListJobs(files: FileList | File[]): DropJob[] {
  return Array.from(files).map((file) => ({
    kind: "file" as const,
    file,
    relativePath: (file.webkitRelativePath || file.name).replace(/\\/g, "/"),
  }));
}

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

function UploadProgressPanel({
  items,
  onDismiss,
}: {
  items: UploadItem[];
  onDismiss: () => void;
}) {
  const done = items.every((i) => i.status === "done" || i.status === "error");
  const overall =
    items.length === 0
      ? 0
      : Math.round(items.reduce((sum, i) => sum + i.percent, 0) / items.length);

  return (
    <div className="fixed bottom-4 right-4 z-[55] w-full max-w-sm rounded border border-cp-border bg-white shadow-xl dark:border-ink-700 dark:bg-ink-950">
      <div className="flex items-center justify-between border-b border-cp-border px-3 py-2 dark:border-ink-800">
        <p className="text-sm font-semibold">
          {done ? "Upload terminé" : `Upload en cours… ${overall}%`}
        </p>
        {done && (
          <button type="button" className="rounded p-1 hover:bg-cp-canvas" onClick={onDismiss} aria-label="Fermer">
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className="space-y-3 p-3">
        <div className="h-2 overflow-hidden rounded bg-cp-canvas">
          <div
            className={`h-full rounded transition-all duration-200 ${
              items.some((i) => i.status === "error") ? "bg-cp-danger" : "bg-cp-orange"
            }`}
            style={{ width: `${overall}%` }}
          />
        </div>
        <ul className="max-h-40 space-y-2 overflow-y-auto text-xs">
          {items.map((item) => (
            <li key={item.name + item.size}>
              <div className="mb-1 flex justify-between gap-2">
                <span className="truncate font-medium text-cp-text" title={item.name}>
                  {item.name}
                </span>
                <span className="shrink-0 text-cp-muted">
                  {item.status === "error"
                    ? "Erreur"
                    : item.status === "done"
                      ? "OK"
                      : `${item.percent}%`}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded bg-cp-canvas">
                <div
                  className={`h-full rounded transition-all ${
                    item.status === "error" ? "bg-cp-danger" : "bg-cp-link"
                  }`}
                  style={{ width: `${item.percent}%` }}
                />
              </div>
              {item.error && <p className="mt-0.5 text-cp-danger">{item.error}</p>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

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
  const [editor, setEditor] = useState<{ path: string; content: string; original: string } | null>(
    null,
  );
  const [chmodPath, setChmodPath] = useState<string | null>(null);
  const [chmodMode, setChmodMode] = useState("644");
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [uploads, setUploads] = useState<UploadItem[] | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameOpen, setRenameOpen] = useState(false);
  const [dropTargetPath, setDropTargetPath] = useState<string | null>(null);
  const [internalDrag, setInternalDrag] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["files", cwd],
    queryFn: () => apiRequest<Listing>(`/files/?path=${encodeURIComponent(cwd)}`),
    placeholderData: (prev) => prev,
    staleTime: 15_000,
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

  const uploadJobs = async (jobs: DropJob[], destCwd: string = cwd) => {
    if (!jobs.length) return;
    setError(null);
    const items: UploadItem[] = jobs.map((job) => ({
      name: job.relativePath,
      size: job.kind === "file" ? job.file.size : 0,
      percent: 0,
      status: "pending",
    }));
    setUploads(items);

    let failed = false;
    for (let i = 0; i < jobs.length; i++) {
      const job = jobs[i];
      setUploads((prev) =>
        prev
          ? prev.map((it, idx) =>
              idx === i ? { ...it, status: "uploading", percent: 0 } : it,
            )
          : prev,
      );
      try {
        if (job.kind === "dir") {
          await apiRequest("/files/mkdir/", {
            method: "POST",
            body: JSON.stringify({
              path: destCwd,
              name: job.relativePath,
              recursive: true,
            }),
          });
        } else {
          await uploadWithProgress(job.file, destCwd, token, (percent) => {
            setUploads((prev) =>
              prev ? prev.map((it, idx) => (idx === i ? { ...it, percent } : it)) : prev,
            );
          }, job.relativePath);
        }
        setUploads((prev) =>
          prev
            ? prev.map((it, idx) =>
                idx === i ? { ...it, status: "done", percent: 100 } : it,
              )
            : prev,
        );
      } catch (err) {
        failed = true;
        const message =
          err instanceof ApiClientError
            ? err.message
            : err instanceof Error
              ? err.message
              : "Upload échoué.";
        setUploads((prev) =>
          prev
            ? prev.map((it, idx) =>
                idx === i ? { ...it, status: "error", error: message } : it,
              )
            : prev,
        );
        setError(message);
      }
    }
    await qc.invalidateQueries({ queryKey: ["files"] });
    if (!failed) setSelected([]);
  };

  const uploadFiles = async (files: FileList | File[], destCwd: string = cwd) => {
    await uploadJobs(collectFileListJobs(files), destCwd);
  };

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
        <button type="button" className="vz-btn-primary vz-btn-sm" onClick={() => fileInputRef.current?.click()}>
          <Upload className="h-3 w-3" />
          Upload
        </button>
        <button type="button" className="vz-btn-ghost vz-btn-sm" onClick={() => folderInputRef.current?.click()}>
          <FolderPlus className="h-3 w-3" />
          Dossier
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
        <input
          ref={folderInputRef}
          type="file"
          className="hidden"
          multiple
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
          onChange={(e) => {
            if (e.target.files?.length) void uploadFiles(e.target.files);
            e.target.value = "";
          }}
        />
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
            void (async () => {
              try {
                const jobs = await collectDataTransferJobs(e.dataTransfer);
                await uploadJobs(jobs, cwd);
              } catch (err) {
                setError(
                  err instanceof Error ? err.message : "Impossible de lire le dépôt.",
                );
              }
            })();
          }}
        >
          <table className="min-w-full text-left text-xs">
            <thead className="sticky top-0 bg-cp-canvas text-[10px] uppercase tracking-wide text-cp-muted dark:bg-ink-900">
              <tr>
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
                    void (async () => {
                      const jobs = await collectDataTransferJobs(e.dataTransfer);
                      await uploadJobs(jobs, parent);
                    })();
                  }}
                >
                  <td className="px-2 py-1 font-medium" colSpan={4}>
                    ..
                  </td>
                </tr>
              )}
              {isLoading && !data && (
                <tr>
                  <td className="px-2 py-3 text-cp-muted" colSpan={4}>
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
                    onClick={(e) => toggleSelect(entry.path, e.ctrlKey || e.metaKey)}
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
                      void (async () => {
                        try {
                          const jobs = await collectDataTransferJobs(e.dataTransfer);
                          await uploadJobs(jobs, entry.path);
                        } catch (err) {
                          setError(
                            err instanceof Error
                              ? err.message
                              : "Impossible de lire le dépôt.",
                          );
                        }
                      })();
                    }}
                  >
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
              Glissez-déposez des fichiers ou dossiers, ou utilisez Upload / Dossier.
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

      {uploads && <UploadProgressPanel items={uploads} onDismiss={() => setUploads(null)} />}
    </div>
  );
}
