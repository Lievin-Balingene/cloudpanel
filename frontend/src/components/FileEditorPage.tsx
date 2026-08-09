import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, Loader2, Save } from "lucide-react";
import { apiRequest, ApiClientError } from "@/lib/api";
import { notifyFilesChanged, resolvePanelBase } from "@/lib/fileEditor";

type EditorState = {
  path: string;
  content: string;
  original: string;
  encoding?: string;
};

export function FileEditorPage() {
  const [params] = useSearchParams();
  const filePath = (params.get("path") || "").replace(/^\/+/, "");
  const panelBase = resolvePanelBase(window.location.pathname);
  const filesHome = `${panelBase}/files`;

  const [editor, setEditor] = useState<EditorState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);

  const dirty = useMemo(
    () => Boolean(editor && editor.content !== editor.original),
    [editor],
  );

  const load = useCallback(async () => {
    if (!filePath) {
      setError("Aucun fichier spécifié (?path=…).");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<{
        path: string;
        content: string;
        encoding?: string;
      }>(`/files/read/?path=${encodeURIComponent(filePath)}`);
      setEditor({
        path: data.path || filePath,
        content: data.content ?? "",
        original: data.content ?? "",
        encoding: data.encoding,
      });
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Impossible de lire le fichier.";
      setError(message);
      setEditor(null);
    } finally {
      setLoading(false);
    }
  }, [filePath]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        const btn = document.getElementById("file-editor-save");
        btn?.click();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function save() {
    if (!editor || !dirty || saving) return;
    setSaving(true);
    setError(null);
    setSavedFlash(false);
    try {
      await apiRequest("/files/write/", {
        method: "PUT",
        body: JSON.stringify({ path: editor.path, content: editor.content }),
      });
      setEditor({ ...editor, original: editor.content });
      setSavedFlash(true);
      notifyFilesChanged(editor.path.split("/").slice(0, -1).join("/"));
      window.setTimeout(() => setSavedFlash(false), 2500);
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Enregistrement impossible.";
      setError(message);
    } finally {
      setSaving(false);
    }
  }

  const title = editor?.path || filePath || "Éditeur";

  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col gap-3 p-3 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Link
            to={filesHome}
            className="mb-1 inline-flex items-center gap-1 text-xs text-cp-muted hover:text-cp-link"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            File Manager
          </Link>
          <h1 className="truncate font-display text-lg font-semibold text-cp-text" title={title}>
            {title}
            {dirty ? (
              <span className="ml-2 text-xs font-normal text-cp-orange">• modifié</span>
            ) : null}
          </h1>
          {editor?.encoding ? (
            <p className="text-xs text-cp-muted">Encodage lecture : {editor.encoding}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {savedFlash ? (
            <span className="text-xs font-medium text-emerald-600">Enregistré</span>
          ) : null}
          <button
            id="file-editor-save"
            type="button"
            className="vz-btn-primary inline-flex items-center gap-2"
            disabled={!editor || !dirty || saving || loading}
            onClick={() => void save()}
            title="Ctrl+S"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {saving ? "Enregistrement…" : "Enregistrer"}
          </button>
          <button
            type="button"
            className="vz-btn-ghost"
            onClick={() => {
              if (dirty && !window.confirm("Fermer sans enregistrer les modifications ?")) {
                return;
              }
              if (window.opener && !window.opener.closed) {
                window.close();
              } else {
                window.location.href = filesHome;
              }
            }}
          >
            Fermer
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded border border-cp-danger/40 bg-cp-danger/10 px-3 py-2 text-sm text-cp-danger">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="vz-panel flex flex-1 items-center justify-center gap-2 p-8 text-cp-muted">
          <Loader2 className="h-5 w-5 animate-spin" />
          Chargement du fichier…
        </div>
      ) : editor ? (
        <div className="vz-panel flex min-h-0 flex-1 flex-col overflow-hidden">
          <textarea
            className="min-h-[min(70vh,720px)] w-full flex-1 resize-y border-0 bg-cp-canvas p-4 font-mono text-sm leading-relaxed text-cp-text outline-none dark:bg-ink-900"
            value={editor.content}
            onChange={(e) => setEditor({ ...editor, content: e.target.value })}
            spellCheck={false}
            aria-label={`Contenu de ${editor.path}`}
          />
        </div>
      ) : (
        <div className="vz-panel p-6 text-sm text-cp-muted">
          Impossible d&apos;ouvrir ce fichier.
          <div className="mt-3">
            <Link to={filesHome} className="text-cp-link hover:underline">
              Retour au File Manager
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
