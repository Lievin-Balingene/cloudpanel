/** Upload fichiers File Manager — logique partagée + handoff vers onglet dédié. */

import { apiRequest, ApiClientError } from "@/lib/api";

export type DropJob =
  | { kind: "file"; file: File; relativePath: string }
  | { kind: "dir"; relativePath: string };

export type UploadItem = {
  name: string;
  size: number;
  percent: number;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
};

export const UPLOAD_MSG = {
  READY: "vzone-upload-ready",
  JOBS: "vzone-upload-jobs",
  DONE: "vzone-upload-done",
} as const;

export const FILES_BROADCAST = "vzone-files";

const SIMPLE_UPLOAD_MAX = 1024 * 1024; // 1 Mo
const CHUNK_BYTES = 2 * 1024 * 1024;
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
      if (event.lengthComputable && options?.onProgress) {
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
  body.append("file", file);
  body.append("path", cwd);
  if (relativePath) body.append("relative_path", relativePath);
  await xhrSend("POST", "/api/v1/files/upload/", token, body, {
    onProgress: (loaded, total) => onProgress(total ? Math.round((loaded / total) * 100) : 0),
  });
}

async function uploadChunkWithRetry(
  uploadId: string,
  index: number,
  blob: Blob,
  token: string | null,
  onChunkProgress: (ratio: number) => void,
): Promise<void> {
  let lastErr: unknown;
  for (let attempt = 0; attempt < CHUNK_RETRIES; attempt++) {
    try {
      const url =
        `/api/v1/files/upload/chunk/?upload_id=${encodeURIComponent(uploadId)}` +
        `&index=${index}`;
      await xhrSend("POST", url, token, blob, {
        contentType: "application/octet-stream",
        onProgress: (loaded, total) => onChunkProgress(total ? loaded / total : 0),
      });
      return;
    } catch (err) {
      lastErr = err;
      await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
    }
  }
  throw lastErr;
}

async function uploadChunked(
  file: File,
  cwd: string,
  token: string | null,
  onProgress: (percent: number) => void,
  relativePath?: string,
): Promise<void> {
  const initRaw = await xhrSend(
    "POST",
    "/api/v1/files/upload/init/",
    token,
    JSON.stringify({
      path: cwd,
      name: file.name,
      size: file.size,
      relative_path: relativePath || "",
      chunk_size: CHUNK_BYTES,
    }),
    { contentType: "application/json" },
  );
  const init = (initRaw as { data?: { upload_id: string; chunk_size: number; total_chunks: number } })
    .data;
  if (!init?.upload_id) {
    throw new ApiClientError("Réponse init upload invalide.", 0);
  }

  const chunkSize = init.chunk_size || CHUNK_BYTES;
  const totalChunks = init.total_chunks || Math.ceil(file.size / chunkSize) || 1;

  try {
    for (let index = 0; index < totalChunks; index++) {
      const start = index * chunkSize;
      const blob = file.slice(start, Math.min(start + chunkSize, file.size));
      await uploadChunkWithRetry(init.upload_id, index, blob, token, (ratio) => {
        const overall = ((index + ratio) / totalChunks) * 100;
        onProgress(Math.min(99, Math.round(overall)));
      });
    }
    await xhrSend(
      "POST",
      "/api/v1/files/upload/complete/",
      token,
      JSON.stringify({ upload_id: init.upload_id }),
      { contentType: "application/json" },
    );
    onProgress(100);
  } catch (err) {
    try {
      await xhrSend(
        "POST",
        "/api/v1/files/upload/abort/",
        token,
        JSON.stringify({ upload_id: init.upload_id }),
        { contentType: "application/json" },
      );
    } catch {
      /* ignore */
    }
    throw err;
  }
}

export async function uploadWithProgress(
  file: File,
  cwd: string,
  token: string | null,
  onProgress: (percent: number) => void,
  relativePath?: string,
): Promise<void> {
  if (file.size <= SIMPLE_UPLOAD_MAX) {
    try {
      await uploadSimple(file, cwd, token, onProgress, relativePath);
      return;
    } catch {
      /* repli chunké */
    }
  }
  await uploadChunked(file, cwd, token, onProgress, relativePath);
}

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

export async function collectDataTransferJobs(dt: DataTransfer): Promise<DropJob[]> {
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

  for (const file of Array.from(dt.files || [])) {
    const rel = (file.webkitRelativePath || file.name).replace(/\\/g, "/");
    jobs.push({ kind: "file", file, relativePath: rel });
  }
  return jobs;
}

export function collectFileListJobs(files: FileList | File[]): DropJob[] {
  return Array.from(files).map((file) => ({
    kind: "file" as const,
    file,
    relativePath: (file.webkitRelativePath || file.name).replace(/\\/g, "/"),
  }));
}

export async function runUploadJobs(
  jobs: DropJob[],
  destCwd: string,
  token: string | null,
  onUpdate: (items: UploadItem[]) => void,
): Promise<{ failed: boolean; items: UploadItem[] }> {
  const items: UploadItem[] = jobs.map((job) => ({
    name: job.relativePath,
    size: job.kind === "file" ? job.file.size : 0,
    percent: 0,
    status: "pending",
  }));
  onUpdate([...items]);

  let failed = false;
  for (let i = 0; i < jobs.length; i++) {
    const job = jobs[i];
    items[i] = { ...items[i], status: "uploading", percent: 0 };
    onUpdate([...items]);
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
          items[i] = { ...items[i], percent };
          onUpdate([...items]);
        }, job.relativePath);
      }
      items[i] = { ...items[i], status: "done", percent: 100 };
      onUpdate([...items]);
    } catch (err) {
      failed = true;
      const message =
        err instanceof ApiClientError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Upload échoué.";
      items[i] = { ...items[i], status: "error", error: message };
      onUpdate([...items]);
    }
  }
  return { failed, items };
}

export function notifyFilesChanged(path: string): void {
  try {
    const bc = new BroadcastChannel(FILES_BROADCAST);
    bc.postMessage({ type: "invalidate", path });
    bc.close();
  } catch {
    /* BroadcastChannel indisponible */
  }
  if (window.opener && !window.opener.closed) {
    try {
      window.opener.postMessage(
        { type: UPLOAD_MSG.DONE, path },
        window.location.origin,
      );
    } catch {
      /* ignore */
    }
  }
}

export type PanelBase = "/whm" | "/panel";

export function resolvePanelBase(pathname: string): PanelBase {
  return pathname.startsWith("/whm") ? "/whm" : "/panel";
}

export function uploadPageUrl(
  base: PanelBase,
  destPath: string,
  options?: { handoff?: string; folder?: boolean },
): string {
  const q = new URLSearchParams();
  q.set("path", destPath);
  if (options?.handoff) q.set("handoff", options.handoff);
  if (options?.folder) q.set("folder", "1");
  return `${base}/files/upload?${q.toString()}`;
}

/** Ouvre l'onglet Upload (style cPanel). Optionnellement transfère des jobs déjà sélectionnés. */
export function openUploadTab(
  base: PanelBase,
  destPath: string,
  options?: { jobs?: DropJob[]; preferFolder?: boolean },
): Window | null {
  const jobs = options?.jobs;
  const handoffId = jobs?.length ? crypto.randomUUID() : undefined;
  const url = uploadPageUrl(base, destPath, {
    handoff: handoffId,
    folder: options?.preferFolder && !jobs?.length,
  });

  let win: Window | null = null;

  const onMessage = (event: MessageEvent) => {
    if (event.origin !== window.location.origin) return;
    if (!win || event.source !== win) return;
    const data = event.data;
    if (!jobs?.length || !handoffId) return;
    if (data?.type === UPLOAD_MSG.READY && data.handoff === handoffId) {
      win.postMessage(
        {
          type: UPLOAD_MSG.JOBS,
          handoff: handoffId,
          dest: destPath,
          jobs: jobs.map((j) =>
            j.kind === "dir"
              ? { kind: "dir", relativePath: j.relativePath }
              : { kind: "file", relativePath: j.relativePath, file: j.file },
          ),
        },
        window.location.origin,
      );
      window.removeEventListener("message", onMessage);
    }
  };

  if (jobs?.length && handoffId) {
    window.addEventListener("message", onMessage);
    window.setTimeout(() => window.removeEventListener("message", onMessage), 90_000);
  }

  win = window.open(url, "_blank");
  if (!win) {
    window.removeEventListener("message", onMessage);
    return null;
  }
  return win;
}
