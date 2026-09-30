import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound, Loader2, RotateCcw, Settings2, Wifi } from "lucide-react";
import { apiRequest } from "@/lib/api";

export type AiProviderMode = "server" | "ollama" | "openai_compat";

export interface ByokSettings {
  mode: AiProviderMode;
  base_url: string;
  model_name: string;
  has_api_key: boolean;
  enabled: boolean;
  last_test_ok: boolean | null;
  last_test_message: string;
  last_tested_at: string | null;
  is_byok_active: boolean;
}

interface ProviderPayload {
  byok_enabled: boolean;
  settings: ByokSettings;
  provider_source: string;
  active_provider: string;
  active_model: string;
}

interface TestResult {
  ok: boolean;
  provider: string;
  model: string;
  message: string;
  models?: string[];
}

const MODE_HELP: Record<AiProviderMode, string> = {
  server: "Utilise le modèle configuré par l'hébergeur (Ollama serveur ou mock).",
  ollama:
    "Votre instance Ollama (PC / VPS). L'URL doit être joignable depuis le serveur (tunnel HTTPS recommandé).",
  openai_compat:
    "OpenAI, Gemini, OpenRouter, Groq, vLLM… — endpoint compatible OpenAI + clé API.",
};

const PRESETS: { id: string; label: string; mode: AiProviderMode; base_url: string; model_name: string }[] = [
  {
    id: "gemini",
    label: "Gemini 3.5",
    mode: "openai_compat",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
    model_name: "gemini-3.5-flash",
  },
  {
    id: "gemini37",
    label: "Gemini 3.7",
    mode: "openai_compat",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
    model_name: "gemini-3.7-flash",
  },
  {
    id: "openai",
    label: "OpenAI",
    mode: "openai_compat",
    base_url: "https://api.openai.com/v1",
    model_name: "gpt-4o-mini",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    mode: "openai_compat",
    base_url: "https://openrouter.ai/api/v1",
    model_name: "openai/gpt-4o-mini",
  },
];

export function AiProviderSettingsPanel({ onClose }: { onClose?: () => void }) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<AiProviderMode>("server");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelName, setModelName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["ai-provider"],
    queryFn: () => apiRequest<ProviderPayload>("/ai/provider/"),
  });

  useEffect(() => {
    const s = query.data?.settings;
    if (!s) return;
    setMode(s.mode);
    setBaseUrl(s.base_url || "");
    setModelName(s.model_name || "");
    setApiKey("");
    setClearKey(false);
  }, [query.data]);

  const saveMut = useMutation({
    mutationFn: () =>
      apiRequest<ProviderPayload>("/ai/provider/", {
        method: "PUT",
        body: JSON.stringify({
          mode,
          base_url: baseUrl,
          model_name: modelName,
          api_key: apiKey || undefined,
          clear_api_key: clearKey,
          enabled: true,
        }),
      }),
    onSuccess: () => {
      setFeedback("Configuration enregistrée.");
      setApiKey("");
      setClearKey(false);
      void qc.invalidateQueries({ queryKey: ["ai-provider"] });
      void qc.invalidateQueries({ queryKey: ["ai-status"] });
    },
    onError: (err: Error) => setFeedback(err.message || "Échec enregistrement"),
  });

  const testMut = useMutation({
    mutationFn: () =>
      apiRequest<TestResult>("/ai/provider/test/", {
        method: "POST",
        body: JSON.stringify({
          mode,
          base_url: baseUrl,
          model_name: modelName,
          api_key: apiKey || undefined,
          use_saved_key: !apiKey && !clearKey,
        }),
      }),
    onSuccess: (data) => {
      setFeedback(data.ok ? data.message : `Échec : ${data.message}`);
      void qc.invalidateQueries({ queryKey: ["ai-provider"] });
    },
    onError: (err: Error) => setFeedback(err.message || "Test échoué"),
  });

  const resetMut = useMutation({
    mutationFn: () =>
      apiRequest<ProviderPayload>("/ai/provider/", { method: "DELETE" }),
    onSuccess: () => {
      setFeedback("Retour au provider serveur.");
      void qc.invalidateQueries({ queryKey: ["ai-provider"] });
      void qc.invalidateQueries({ queryKey: ["ai-status"] });
    },
  });

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-6 text-sm text-cp-muted">
        <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
      </div>
    );
  }

  if (query.data && !query.data.byok_enabled) {
    return (
      <div className="space-y-3 p-4 text-sm">
        <p className="font-medium text-cp-text">Modèle IA</p>
        <p className="text-cp-muted">
          Le BYOK est désactivé par l&apos;administrateur. Vous utilisez le provider serveur (
          {query.data.active_provider}
          {query.data.active_model ? ` · ${query.data.active_model}` : ""}).
        </p>
        {onClose && (
          <button type="button" className="text-xs text-cp-navy underline" onClick={onClose}>
            Fermer
          </button>
        )}
      </div>
    );
  }

  const busy = saveMut.isPending || testMut.isPending || resetMut.isPending;
  const showFields = mode !== "server";

  return (
    <div className="flex max-h-full flex-col overflow-y-auto border-b border-cp-border bg-cp-canvas/90 p-3 dark:bg-black/30">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-sm font-semibold text-cp-text dark:text-white">
          <Settings2 className="h-4 w-4" />
          Mon modèle IA
        </div>
        {onClose && (
          <button
            type="button"
            className="text-[11px] text-cp-muted hover:text-cp-text"
            onClick={onClose}
          >
            Fermer
          </button>
        )}
      </div>

      <p className="mb-3 text-[11px] leading-snug text-cp-muted">{MODE_HELP[mode]}</p>

      <div className="mb-3 flex flex-wrap gap-1">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            disabled={busy}
            onClick={() => {
              setMode(p.mode);
              setBaseUrl(p.base_url);
              setModelName(p.model_name);
              setFeedback(`Preset ${p.label} — collez votre clé API puis Tester / Enregistrer.`);
            }}
            className="rounded-lg bg-white px-2 py-1 text-[10px] font-medium text-cp-text ring-1 ring-cp-border hover:bg-cp-canvas dark:bg-white/10 dark:text-white"
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setMode("server");
            setBaseUrl("");
            setModelName("");
            setFeedback(null);
          }}
          className="rounded-lg px-2 py-1 text-[10px] font-medium text-cp-muted hover:bg-black/5 dark:hover:bg-white/5"
        >
          Serveur
        </button>
      </div>

      <label className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-cp-muted">
        Provider
      </label>
      <select
        className="mb-3 w-full rounded-xl border border-cp-border bg-white px-3 py-2 text-sm dark:bg-black/40 dark:text-white"
        value={mode}
        onChange={(e) => setMode(e.target.value as AiProviderMode)}
        disabled={busy}
      >
        <option value="server">Serveur (défaut panel)</option>
        <option value="ollama">Ollama (URL perso)</option>
        <option value="openai_compat">API OpenAI-compatible</option>
      </select>

      {showFields && (
        <>
          <label className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-cp-muted">
            URL
          </label>
          <input
            className="mb-3 w-full rounded-xl border border-cp-border bg-white px-3 py-2 text-sm dark:bg-black/40 dark:text-white"
            placeholder={
              mode === "ollama"
                ? "https://ollama.mondomaine.com"
                : "https://api.openai.com/v1"
            }
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />

          <label className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-cp-muted">
            Modèle
          </label>
          <input
            className="mb-3 w-full rounded-xl border border-cp-border bg-white px-3 py-2 text-sm dark:bg-black/40 dark:text-white"
            placeholder={mode === "ollama" ? "llama3.2" : "gpt-4o-mini"}
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />

          {mode === "openai_compat" && (
            <>
              <label className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-cp-muted">
                <KeyRound className="h-3 w-3" /> Clé API
              </label>
              <input
                type="password"
                className="mb-1 w-full rounded-xl border border-cp-border bg-white px-3 py-2 text-sm dark:bg-black/40 dark:text-white"
                placeholder={
                  query.data?.settings.has_api_key && !clearKey
                    ? "•••••••• (inchangée si vide)"
                    : "sk-…"
                }
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setClearKey(false);
                }}
                disabled={busy}
                autoComplete="new-password"
              />
              {query.data?.settings.has_api_key && (
                <label className="mb-3 flex items-center gap-2 text-[11px] text-cp-muted">
                  <input
                    type="checkbox"
                    checked={clearKey}
                    onChange={(e) => {
                      setClearKey(e.target.checked);
                      if (e.target.checked) setApiKey("");
                    }}
                  />
                  Effacer la clé enregistrée
                </label>
              )}
            </>
          )}
        </>
      )}

      {feedback && (
        <p
          className={`mb-2 rounded-lg px-2.5 py-1.5 text-[11px] ${
            feedback.toLowerCase().includes("échec") || feedback.toLowerCase().includes("interdit")
              ? "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-100"
              : "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100"
          }`}
        >
          {feedback}
        </p>
      )}

      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          disabled={busy}
          onClick={() => testMut.mutate()}
          className="inline-flex items-center gap-1 rounded-lg bg-white px-2.5 py-1.5 text-[11px] font-medium text-cp-text ring-1 ring-cp-border hover:bg-cp-canvas disabled:opacity-50 dark:bg-white/10 dark:text-white"
        >
          {testMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wifi className="h-3 w-3" />}
          Tester
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => saveMut.mutate()}
          className="inline-flex items-center gap-1 rounded-lg bg-cp-navy px-2.5 py-1.5 text-[11px] font-medium text-white hover:bg-cp-navy-soft disabled:opacity-50"
        >
          {saveMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
          Enregistrer
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => resetMut.mutate()}
          className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-cp-muted hover:bg-black/5 dark:hover:bg-white/5"
        >
          <RotateCcw className="h-3 w-3" />
          Défaut serveur
        </button>
      </div>

      {query.data?.settings.last_test_message && (
        <p className="mt-2 text-[10px] text-cp-muted">
          Dernier test :{" "}
          <span className={query.data.settings.last_test_ok ? "text-emerald-600" : "text-amber-600"}>
            {query.data.settings.last_test_message}
          </span>
        </p>
      )}
    </div>
  );
}
