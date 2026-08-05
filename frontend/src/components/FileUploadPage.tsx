import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FolderOpen, FolderPlus, Trash2, Upload, X } from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { formatBytes } from "@/lib/format";
import {
  collectDataTransferJobs,
  collectFileListJobs,
  DropJob,
  notifyFilesChanged,
  resolvePanelBase,
  runUploadJobs,
  UPLOAD_MSG,
  UploadItem,
} from "@/lib/fileUpload";

function mergeJobs(existing: DropJob[], incoming: DropJob[]): DropJob[] {
  const map = new Map(existing.map((j) => [j.relativePath, j]));
  for (const job of incoming) {
    map.set(job.relativePath, job);
  }
  return Array.from(map.values());
}

function ProgressList({ items }: { items: UploadItem[] }) {
  const done = items.every((i) => i.status === "done" || i.status === "error");
  const overall =
    items.length === 0
      ? 0
      : Math.round(items.reduce((sum, i) => sum + i.percent, 0) / items.length);
  const hasError = items.some((i) => i.status === "error");

  return (
    <div className="vz-panel space-y-4 p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-cp-text">
          {done
            ? hasError
              ? "Upload terminé avec des erreurs"
              : "Upload terminé"
            : `Upload en cours… ${overall}%`}
        </h2>
        <span className="text-xs text-cp-muted">
          {items.filter((i) => i.status === "done").length}/{items.length}
        </span>
      </div>
      <div className="h-2.5 overflow-hidden rounded bg-cp-canvas">
        <div
          className={`h-full rounded transition-all duration-200 ${
            hasError ? "bg-cp-danger" : "bg-cp-orange"
          }`}
          style={{ width: `${overall}%` }}
        />
      </div>
      <ul className="max-h-[min(50vh,420px)] space-y-3 overflow-y-auto text-sm">
        {items.map((item, idx) => (
          <li key={`${item.name}-${idx}`}>
            <div className="mb-1 flex justify-between gap-2">
              <span className="truncate font-medium text-cp-text" title={item.name}>
                {item.name}
              </span>
              <span className="shrink-0 text-xs text-cp-muted">
                {item.status === "error"
                  ? "Erreur"
                  : item.status === "done"
                    ? "OK"
                    : item.status === "pending"
                      ? "En attente"
                      : `${item.percent}%`}
                {item.size > 0 ? ` · ${formatBytes(item.size)}` : ""}
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
            {item.error && <p className="mt-1 text-xs text-cp-danger">{item.error}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function FileUploadPage() {
  const token = useAuthStore((s) => s.accessToken);
  const [params] = useSearchParams();
  const destPath = params.get("path") ?? "";
  const handoff = params.get("handoff") ?? "";
  const preferFolder = params.get("folder") === "1";

  const base = resolvePanelBase(window.location.pathname);
  const filesHome = `${base}/files`;

  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const startedRef = useRef(false);

  const [queue, setQueue] = useState<DropJob[]>([]);
  const [items, setItems] = useState<UploadItem[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [finished, setFinished] = useState(false);

  const destLabel = useMemo(() => (destPath ? `~/${destPath}` : "~/"), [destPath]);
  const queueBytes = useMemo(
    () => queue.reduce((sum, j) => sum + (j.kind === "file" ? j.file.size : 0), 0),
    [queue],
  );

  const addToQueue = useCallback((jobs: DropJob[]) => {
    if (!jobs.length) return;
    setQueue((prev) => mergeJobs(prev, jobs));
    setError(null);
  }, []);

  const startJobs = useCallback(
    async (jobs: DropJob[]) => {
      if (!jobs.length || busy) return;
      setBusy(true);
      setFinished(false);
      setError(null);
      setQueue([]);
      const { failed } = await runUploadJobs(jobs, destPath, token, setItems);
      setBusy(false);
      setFinished(true);
      notifyFilesChanged(destPath);
      if (failed) {
        setError("Certains fichiers n'ont pas pu être envoyés.");
      }
    },
    [busy, destPath, token],
  );

  const startQueued = useCallback(() => {
    if (!queue.length) return;
    void startJobs(queue);
  }, [queue, startJobs]);

  // Handoff depuis le File Manager (glisser-déposer / sélection) → démarre tout de suite
  useEffect(() => {
    if (!handoff || startedRef.current) return;

    let ping = 0;

    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      const data = event.data;
      if (data?.type !== UPLOAD_MSG.JOBS || data.handoff !== handoff) return;
      if (startedRef.current) return;
      startedRef.current = true;
      window.clearInterval(ping);
      const rawJobs = Array.isArray(data.jobs) ? data.jobs : [];
      const jobs: DropJob[] = rawJobs
        .map((j: { kind?: string; relativePath?: string; file?: File }) => {
          if (j.kind === "dir" && j.relativePath) {
            return { kind: "dir" as const, relativePath: String(j.relativePath) };
          }
          if (j.kind === "file" && j.file instanceof File) {
            return {
              kind: "file" as const,
              file: j.file,
              relativePath: String(j.relativePath || j.file.name),
            };
          }
          return null;
        })
        .filter((j: DropJob | null): j is DropJob => Boolean(j));
      void startJobs(jobs);
    };

    const pingReady = () => {
      if (window.opener && !window.opener.closed) {
        window.opener.postMessage(
          { type: UPLOAD_MSG.READY, handoff },
          window.location.origin,
        );
      }
    };

    window.addEventListener("message", onMessage);
    pingReady();
    ping = window.setInterval(pingReady, 400);
    const stop = window.setTimeout(() => window.clearInterval(ping), 30_000);

    return () => {
      window.removeEventListener("message", onMessage);
      window.clearInterval(ping);
      window.clearTimeout(stop);
    };
  }, [handoff, startJobs]);

  useEffect(() => {
    if (preferFolder && !handoff) {
      const t = window.setTimeout(() => folderInputRef.current?.click(), 200);
      return () => window.clearTimeout(t);
    }
  }, [preferFolder, handoff]);

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-cp-muted">
            File Manager
          </p>
          <h1 className="text-xl font-bold text-cp-text">Upload Files</h1>
          <p className="mt-1 text-sm text-cp-muted">
            Destination : <span className="font-medium text-cp-text">{destLabel}</span>
          </p>
        </div>
        <Link to={filesHome} className="vz-btn-ghost vz-btn-sm">
          <FolderOpen className="h-3 w-3" />
          Retour au File Manager
        </Link>
      </div>

      {error && (
        <div className="rounded border border-cp-danger/30 bg-red-50 px-3 py-2 text-sm text-cp-danger dark:bg-red-950/40">
          {error}
        </div>
      )}

      {!items && (
        <>
          <div
            className={`vz-panel flex flex-col items-center justify-center gap-4 border-2 border-dashed px-6 py-10 text-center transition ${
              dragOver
                ? "border-cp-orange bg-cp-orange-soft/40"
                : "border-cp-border bg-cp-canvas/40"
            }`}
            onDragEnter={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragOver={(e) => e.preventDefault()}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              void (async () => {
                const jobs = await collectDataTransferJobs(e.dataTransfer);
                addToQueue(jobs);
              })();
            }}
          >
            <Upload className="h-10 w-10 text-cp-orange" />
            <div>
              <p className="text-base font-semibold text-cp-text">
                Ajoutez plusieurs fichiers et dossiers
              </p>
              <p className="mt-1 text-sm text-cp-muted">
                Vous pouvez choisir des fichiers, puis d&apos;autres dossiers, plusieurs fois —
                tout est regroupé avant l&apos;envoi.
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              <button
                type="button"
                className="vz-btn-primary"
                disabled={busy}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="h-4 w-4" />
                Ajouter des fichiers
              </button>
              <button
                type="button"
                className="vz-btn-ghost"
                disabled={busy}
                onClick={() => folderInputRef.current?.click()}
              >
                <FolderPlus className="h-4 w-4" />
                Ajouter un dossier
              </button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) {
                  addToQueue(collectFileListJobs(e.target.files));
                }
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
                if (e.target.files?.length) {
                  addToQueue(collectFileListJobs(e.target.files));
                }
                e.target.value = "";
              }}
            />
          </div>

          {queue.length > 0 && (
            <div className="vz-panel space-y-3 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-cp-text">
                    Prêt à envoyer · {queue.length} élément(s)
                  </h2>
                  <p className="text-xs text-cp-muted">{formatBytes(queueBytes)}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="vz-btn-ghost vz-btn-sm"
                    onClick={() => setQueue([])}
                    disabled={busy}
                  >
                    Vider
                  </button>
                  <button
                    type="button"
                    className="vz-btn-primary"
                    onClick={startQueued}
                    disabled={busy}
                  >
                    <Upload className="h-4 w-4" />
                    Démarrer l&apos;upload
                  </button>
                </div>
              </div>
              <ul className="max-h-56 space-y-1 overflow-y-auto text-sm">
                {queue.map((job) => (
                  <li
                    key={job.relativePath}
                    className="flex items-center justify-between gap-2 rounded px-2 py-1 hover:bg-cp-canvas"
                  >
                    <span className="min-w-0 truncate" title={job.relativePath}>
                      <span className="mr-1.5 text-[10px] font-semibold uppercase text-cp-muted">
                        {job.kind === "dir" ? "dir" : "file"}
                      </span>
                      {job.relativePath}
                      {job.kind === "file" ? (
                        <span className="ml-2 text-xs text-cp-muted">
                          {formatBytes(job.file.size)}
                        </span>
                      ) : (
                        <span className="ml-2 text-xs text-cp-muted">dossier vide</span>
                      )}
                    </span>
                    <button
                      type="button"
                      className="shrink-0 rounded p-1 text-cp-muted hover:bg-white hover:text-cp-danger"
                      onClick={() =>
                        setQueue((prev) =>
                          prev.filter((j) => j.relativePath !== job.relativePath),
                        )
                      }
                      aria-label="Retirer"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {items && <ProgressList items={items} />}

      {finished && items && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="vz-btn-primary"
            onClick={() => {
              setItems(null);
              setFinished(false);
              setError(null);
              setQueue([]);
              startedRef.current = false;
            }}
          >
            Nouvel upload
          </button>
          <Link to={filesHome} className="vz-btn-ghost">
            Fermer et revenir
          </Link>
          <button type="button" className="vz-btn-ghost" onClick={() => window.close()}>
            <X className="h-4 w-4" />
            Fermer l&apos;onglet
          </button>
        </div>
      )}
    </div>
  );
}
