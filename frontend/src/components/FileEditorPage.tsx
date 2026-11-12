import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import AceEditor from "react-ace";
import {
  ArrowLeft,
  Download,
  Keyboard,
  Loader2,
  Redo2,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings2,
  Undo2,
  WrapText,
} from "lucide-react";
import { apiRequest, ApiClientError } from "@/lib/api";
import { notifyFilesChanged, resolvePanelBase } from "@/lib/fileEditor";
import { BRAND } from "@/lib/brand";
import { formatBytes } from "@/lib/format";
import { ensureAceReady } from "@/components/file-editor/aceSetup";
import { ACE_MODES, AceModeId, detectAceMode } from "@/components/file-editor/modes";
import {
  ACE_THEMES,
  AceThemeId,
  EditorPrefs,
  loadEditorPrefs,
  saveEditorPrefs,
} from "@/components/file-editor/settings";

ensureAceReady();

type EditorState = {
  path: string;
  content: string;
  original: string;
  encoding?: string;
  size?: number;
};

type CursorPos = { row: number; column: number };

const SHORTCUTS = [
  { keys: "Ctrl+S", desc: "Enregistrer" },
  { keys: "Ctrl+F", desc: "Rechercher" },
  { keys: "Ctrl+H", desc: "Remplacer" },
  { keys: "Ctrl+G", desc: "Aller à la ligne" },
  { keys: "Ctrl+Z / Y", desc: "Annuler / Rétablir" },
  { keys: "Ctrl+/", desc: "Commenter" },
  { keys: "Ctrl+,", desc: "Options Ace" },
  { keys: "Alt+↑ / ↓", desc: "Déplacer la ligne" },
  { keys: "Ctrl+D", desc: "Supprimer la ligne" },
  { keys: "Esc", desc: "Fermer panneaux" },
];

export function FileEditorPage() {
  const [params] = useSearchParams();
  const filePath = (params.get("path") || "").replace(/^\/+/, "");
  const panelBase = resolvePanelBase(window.location.pathname);
  const filesHome = `${panelBase}/fm`;

  const [editor, setEditor] = useState<EditorState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);
  const [prefs, setPrefs] = useState<EditorPrefs>(() => loadEditorPrefs());
  const [mode, setMode] = useState<AceModeId>(() => detectAceMode(filePath));
  const [cursor, setCursor] = useState<CursorPos>({ row: 0, column: 0 });
  const [showSettings, setShowSettings] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [gotoOpen, setGotoOpen] = useState(false);
  const [gotoValue, setGotoValue] = useState("");
  const aceRef = useRef<AceEditor | null>(null);

  const dirty = useMemo(
    () => Boolean(editor && editor.content !== editor.original),
    [editor],
  );

  const lineCount = useMemo(
    () => (editor ? editor.content.split("\n").length : 0),
    [editor],
  );

  const updatePrefs = useCallback((patch: Partial<EditorPrefs>) => {
    setPrefs((prev) => {
      const next = { ...prev, ...patch };
      saveEditorPrefs(next);
      return next;
    });
  }, []);

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
        size?: number;
      }>(`/files/read/?path=${encodeURIComponent(filePath)}`);
      setEditor({
        path: data.path || filePath,
        content: data.content ?? "",
        original: data.content ?? "",
        encoding: data.encoding,
        size: data.size,
      });
      setMode(detectAceMode(data.path || filePath));
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
    const name = filePath.split("/").pop() || "Éditeur";
    document.title = `${dirty ? "• " : ""}${name} · Éditeur · ${BRAND}`;
  }, [filePath, dirty]);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const getAce = () => aceRef.current?.editor;

  const save = useCallback(async () => {
    if (!editor || editor.content === editor.original || saving) return;
    setSaving(true);
    setError(null);
    setSavedFlash(false);
    try {
      await apiRequest("/files/write/", {
        method: "PUT",
        body: JSON.stringify({ path: editor.path, content: editor.content }),
      });
      setEditor((prev) =>
        prev ? { ...prev, original: prev.content, size: new Blob([prev.content]).size } : prev,
      );
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
  }, [editor, saving]);

  const revert = useCallback(() => {
    if (!editor || !dirty) return;
    if (!window.confirm("Annuler toutes les modifications non enregistrées ?")) return;
    setEditor({ ...editor, content: editor.original });
  }, [editor, dirty]);

  const openFind = useCallback(() => {
    getAce()?.execCommand("find");
  }, []);

  const openReplace = useCallback(() => {
    getAce()?.execCommand("replace");
  }, []);

  const goToLine = useCallback(() => {
    const n = parseInt(gotoValue, 10);
    if (!Number.isFinite(n) || n < 1) return;
    const ed = getAce();
    if (!ed) return;
    ed.gotoLine(n, 0, true);
    ed.focus();
    setGotoOpen(false);
    setGotoValue("");
  }, [gotoValue]);

  const downloadCurrent = useCallback(() => {
    if (!editor) return;
    const blob = new Blob([editor.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = editor.path.split("/").pop() || "file.txt";
    a.click();
    URL.revokeObjectURL(url);
  }, [editor]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void save();
      } else if (mod && e.key.toLowerCase() === "g") {
        e.preventDefault();
        setGotoOpen(true);
      } else if (mod && e.key === ",") {
        e.preventDefault();
        setShowSettings((v) => !v);
      } else if (e.key === "Escape") {
        setShowSettings(false);
        setShowShortcuts(false);
        setGotoOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save]);

  function closeEditor() {
    if (dirty && !window.confirm("Fermer sans enregistrer les modifications ?")) return;
    if (window.opener && !window.opener.closed) {
      window.close();
    } else {
      window.location.href = filesHome;
    }
  }

  const fileName = editor?.path.split("/").pop() || filePath.split("/").pop() || "Éditeur";
  const selectCls =
    "h-8 rounded border border-cp-border bg-white px-1.5 text-[11px] text-cp-text dark:border-ink-700 dark:bg-ink-900";

  return (
    <div className="flex h-full min-h-0 flex-col gap-1.5">
      {/* Toolbar style cPanel */}
      <div className="vz-panel flex shrink-0 flex-wrap items-center gap-1.5 px-2 py-1.5">
        <Link
          to={filesHome}
          className="inline-flex h-8 items-center gap-1 rounded px-1.5 text-xs text-cp-muted hover:bg-cp-canvas hover:text-cp-link dark:hover:bg-ink-900"
          title="Retour au File Manager"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">FM</span>
        </Link>

        <div className="min-w-0 flex-1 px-1">
          <p className="truncate text-sm font-semibold text-cp-text" title={editor?.path || filePath}>
            {fileName}
            {dirty ? <span className="ml-1.5 text-xs font-normal text-cp-orange">• modifié</span> : null}
          </p>
          <p className="truncate font-mono text-[10px] text-cp-muted">
            {editor?.path || filePath || "—"}
          </p>
        </div>

        <button
          type="button"
          className="vz-btn-primary vz-btn-sm"
          disabled={!editor || !dirty || saving || loading}
          onClick={() => void save()}
          title="Ctrl+S"
        >
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          <span className="vz-label-sm">{saving ? "…" : "Enregistrer"}</span>
        </button>

        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={!dirty || saving}
          onClick={revert}
          title="Revenir à la version disque"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Annuler</span>
        </button>

        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          disabled={loading}
          onClick={() => {
            if (dirty && !window.confirm("Recharger depuis le disque ? Les modifications seront perdues.")) {
              return;
            }
            void load();
          }}
          title="Recharger"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>

        <span className="mx-0.5 hidden h-5 w-px bg-cp-border sm:block" />

        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={() => getAce()?.undo()}
          title="Annuler (Ctrl+Z)"
        >
          <Undo2 className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={() => getAce()?.redo()}
          title="Rétablir (Ctrl+Y)"
        >
          <Redo2 className="h-3.5 w-3.5" />
        </button>
        <button type="button" className="vz-btn-ghost vz-btn-sm" onClick={openFind} title="Ctrl+F">
          <Search className="h-3.5 w-3.5" />
          <span className="vz-label-sm">Chercher</span>
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={openReplace}
          title="Ctrl+H"
        >
          <span className="vz-label-sm">Remplacer</span>
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={() => setGotoOpen(true)}
          title="Ctrl+G"
        >
          <span className="vz-label-sm">Ligne</span>
        </button>

        <button
          type="button"
          className={`vz-btn-ghost vz-btn-sm ${prefs.wrap ? "bg-cp-orange-soft text-cp-orange-dark" : ""}`}
          onClick={() => updatePrefs({ wrap: !prefs.wrap })}
          title="Retour à la ligne"
        >
          <WrapText className="h-3.5 w-3.5" />
        </button>

        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={downloadCurrent}
          disabled={!editor}
          title="Télécharger"
        >
          <Download className="h-3.5 w-3.5" />
        </button>

        <button
          type="button"
          className={`vz-btn-ghost vz-btn-sm ${showSettings ? "bg-cp-orange-soft" : ""}`}
          onClick={() => setShowSettings((v) => !v)}
          title="Options (Ctrl+,)"
        >
          <Settings2 className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className="vz-btn-ghost vz-btn-sm"
          onClick={() => setShowShortcuts((v) => !v)}
          title="Raccourcis"
        >
          <Keyboard className="h-3.5 w-3.5" />
        </button>

        {savedFlash ? (
          <span className="text-[11px] font-medium text-emerald-600">Enregistré</span>
        ) : null}

        <button type="button" className="vz-btn-ghost vz-btn-sm ml-auto" onClick={closeEditor}>
          Fermer
        </button>
      </div>

      {error ? (
        <div className="shrink-0 rounded-lg border border-cp-danger/40 bg-cp-danger/10 px-3 py-2 text-sm text-cp-danger">
          {error}
        </div>
      ) : null}

      <div className="relative flex min-h-0 flex-1 overflow-hidden rounded-lg border border-cp-border bg-white dark:border-ink-800 dark:bg-ink-950">
        {loading ? (
          <div className="flex flex-1 items-center justify-center gap-2 text-cp-muted">
            <Loader2 className="h-5 w-5 animate-spin" />
            Chargement du fichier…
          </div>
        ) : editor ? (
          <AceEditor
            ref={aceRef}
            mode={mode}
            theme={prefs.theme}
            value={editor.content}
            name="vzone-file-editor"
            width="100%"
            height="100%"
            fontSize={prefs.fontSize}
            showPrintMargin={prefs.showPrintMargin}
            showGutter={prefs.showGutter}
            highlightActiveLine={prefs.highlightActiveLine}
            wrapEnabled={prefs.wrap}
            setOptions={{
              useSoftTabs: prefs.softTabs,
              tabSize: prefs.tabSize,
              showInvisibles: prefs.showInvisibles,
              printMarginColumn: prefs.printMarginColumn,
              enableBasicAutocompletion: true,
              enableLiveAutocompletion: true,
              enableSnippets: true,
              useWorker: false,
              fixedWidthGutter: true,
            }}
            editorProps={{ $blockScrolling: true }}
            onChange={(value) => setEditor({ ...editor, content: value })}
            onCursorChange={(sel) => {
              const pos = sel?.getCursor?.() ?? sel?.cursor;
              if (pos) setCursor({ row: pos.row, column: pos.column });
            }}
            onLoad={(ed) => {
              ed.focus();
              ed.commands.addCommand({
                name: "saveFile",
                bindKey: { win: "Ctrl-S", mac: "Command-S" },
                exec: () => {
                  void save();
                },
              });
            }}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-sm text-cp-muted">
            Impossible d&apos;ouvrir ce fichier.
            <Link to={filesHome} className="text-cp-link hover:underline">
              Retour au File Manager
            </Link>
          </div>
        )}

        {/* Panneau options (persisté) */}
        {showSettings && (
          <aside className="absolute inset-y-0 right-0 z-20 flex w-[min(100%,280px)] flex-col border-l border-cp-border bg-white shadow-xl dark:border-ink-700 dark:bg-ink-950">
            <div className="flex items-center justify-between border-b border-cp-border px-3 py-2 dark:border-ink-800">
              <p className="text-sm font-semibold">Options</p>
              <button
                type="button"
                className="text-xs text-cp-muted hover:text-cp-text"
                onClick={() => setShowSettings(false)}
              >
                Fermer
              </button>
            </div>
            <div className="space-y-3 overflow-auto p-3 text-xs">
              <label className="block space-y-1">
                <span className="text-cp-muted">Thème</span>
                <select
                  className={`${selectCls} w-full`}
                  value={prefs.theme}
                  onChange={(e) => updatePrefs({ theme: e.target.value as AceThemeId })}
                >
                  {ACE_THEMES.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                      {t.dark ? " (sombre)" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1">
                <span className="text-cp-muted">Langage</span>
                <select
                  className={`${selectCls} w-full`}
                  value={mode}
                  onChange={(e) => setMode(e.target.value as AceModeId)}
                >
                  {ACE_MODES.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1">
                <span className="text-cp-muted">Taille police ({prefs.fontSize}px)</span>
                <input
                  type="range"
                  min={11}
                  max={22}
                  value={prefs.fontSize}
                  onChange={(e) => updatePrefs({ fontSize: Number(e.target.value) })}
                  className="w-full accent-cp-orange"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-cp-muted">Tabulation ({prefs.tabSize})</span>
                <input
                  type="range"
                  min={1}
                  max={8}
                  value={prefs.tabSize}
                  onChange={(e) => updatePrefs({ tabSize: Number(e.target.value) })}
                  className="w-full accent-cp-orange"
                />
              </label>
              {(
                [
                  ["wrap", "Retour à la ligne"],
                  ["showGutter", "Numéros de ligne"],
                  ["showInvisibles", "Caractères invisibles"],
                  ["showPrintMargin", "Marge d'impression"],
                  ["highlightActiveLine", "Ligne active"],
                  ["softTabs", "Espaces pour Tab"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="flex items-center justify-between gap-2">
                  <span>{label}</span>
                  <input
                    type="checkbox"
                    className="accent-cp-orange"
                    checked={Boolean(prefs[key])}
                    onChange={(e) => updatePrefs({ [key]: e.target.checked })}
                  />
                </label>
              ))}
              {prefs.showPrintMargin && (
                <label className="block space-y-1">
                  <span className="text-cp-muted">Colonne marge ({prefs.printMarginColumn})</span>
                  <input
                    type="range"
                    min={40}
                    max={160}
                    step={4}
                    value={prefs.printMarginColumn}
                    onChange={(e) =>
                      updatePrefs({ printMarginColumn: Number(e.target.value) })
                    }
                    className="w-full accent-cp-orange"
                  />
                </label>
              )}
              <p className="pt-1 text-[10px] text-cp-muted">
                Préférences enregistrées sur cet appareil (contrairement à cPanel).
              </p>
            </div>
          </aside>
        )}

        {showShortcuts && (
          <aside className="absolute inset-y-0 right-0 z-20 flex w-[min(100%,280px)] flex-col border-l border-cp-border bg-white shadow-xl dark:border-ink-700 dark:bg-ink-950">
            <div className="flex items-center justify-between border-b border-cp-border px-3 py-2 dark:border-ink-800">
              <p className="text-sm font-semibold">Raccourcis</p>
              <button
                type="button"
                className="text-xs text-cp-muted hover:text-cp-text"
                onClick={() => setShowShortcuts(false)}
              >
                Fermer
              </button>
            </div>
            <ul className="space-y-1.5 overflow-auto p-3 text-xs">
              {SHORTCUTS.map((s) => (
                <li key={s.keys} className="flex justify-between gap-2">
                  <kbd className="rounded bg-cp-canvas px-1.5 py-0.5 font-mono text-[10px] dark:bg-ink-900">
                    {s.keys}
                  </kbd>
                  <span className="text-cp-muted">{s.desc}</span>
                </li>
              ))}
            </ul>
          </aside>
        )}
      </div>

      {/* Status bar */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 rounded-md border border-cp-border bg-[#f3f6fa] px-2 py-1 text-[10px] text-cp-muted dark:border-ink-800 dark:bg-ink-950">
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-1">
            Mode
            <select
              className={selectCls}
              value={mode}
              onChange={(e) => setMode(e.target.value as AceModeId)}
            >
              {ACE_MODES.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label className="inline-flex items-center gap-1">
            Thème
            <select
              className={selectCls}
              value={prefs.theme}
              onChange={(e) => updatePrefs({ theme: e.target.value as AceThemeId })}
            >
              {ACE_THEMES.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-3 font-mono">
          <span>
            Ln {cursor.row + 1}, Col {cursor.column + 1}
          </span>
          <span>{lineCount} lignes</span>
          <span>
            {editor?.encoding || "utf-8"}
            {typeof editor?.size === "number" ? ` · ${formatBytes(editor.size)}` : ""}
          </span>
          <span>{prefs.softTabs ? `Spaces: ${prefs.tabSize}` : `Tab: ${prefs.tabSize}`}</span>
          {dirty ? <span className="font-sans text-cp-orange">Non enregistré</span> : null}
        </div>
      </div>

      {gotoOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <form
            className="w-full max-w-xs space-y-3 rounded border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950"
            onSubmit={(e) => {
              e.preventDefault();
              goToLine();
            }}
          >
            <p className="font-semibold">Aller à la ligne</p>
            <input
              className="vz-input"
              type="number"
              min={1}
              max={lineCount || undefined}
              value={gotoValue}
              onChange={(e) => setGotoValue(e.target.value)}
              placeholder={`1 – ${lineCount || "?"}`}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setGotoOpen(false)}>
                Annuler
              </button>
              <button type="submit" className="vz-btn-primary">
                Aller
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
