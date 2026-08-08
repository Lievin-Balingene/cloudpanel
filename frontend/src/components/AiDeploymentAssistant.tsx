import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Bug,
  Check,
  ChevronRight,
  Copy,
  History,
  Loader2,
  MapPin,
  Maximize2,
  Minimize2,
  Plus,
  Send,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { buildUiPageContext } from "@/lib/aiPageContext";

interface AiMessage {
  id?: number;
  role: string;
  content: string;
  created_at?: string;
  metadata?: Record<string, unknown>;
}

interface PendingAction {
  token: string;
  tool_name: string;
  description: string;
  params?: Record<string, unknown>;
  expires_at?: string;
}

interface ConversationSummary {
  id: number;
  title: string;
  updated_at?: string;
  message_count?: number;
}

interface Conversation extends ConversationSummary {
  messages?: AiMessage[];
  context?: Record<string, unknown>;
}

interface Playbook {
  id: string;
  title: string;
  runtime: string;
  prompt: string;
  steps: { id: string; label: string }[];
}

interface SendResult {
  message: AiMessage;
  pending_actions: PendingAction[];
  tool_trace?: { name?: string; ok?: boolean }[];
  provider?: string;
  model?: string;
  ui_context?: { label?: string; section?: string; path?: string };
  suggestions?: string[];
}

interface JailCommand {
  id: string;
  label: string;
  description: string;
  needs_app: boolean;
}

function renderContent(text: string) {
  const blocks = text.split(/(```[\s\S]*?```)/g);
  return blocks.map((block, bi) => {
    if (block.startsWith("```") && block.endsWith("```")) {
      const body = block.replace(/^```\w*\n?/, "").replace(/```$/, "");
      return (
        <pre
          key={bi}
          className="my-2 overflow-x-auto rounded-lg border border-white/10 bg-[#0f172a] p-2.5 text-[11px] leading-relaxed text-emerald-100"
        >
          {body}
        </pre>
      );
    }
    const lines = block.split("\n");
    return (
      <span key={bi}>
        {lines.map((line, li) => {
          const bullet = line.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
          const content = bullet ? bullet[3] : line;
          const inline = content.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
            if (part.startsWith("**") && part.endsWith("**")) {
              return (
                <strong key={i} className="font-semibold">
                  {part.slice(2, -2)}
                </strong>
              );
            }
            if (part.startsWith("`") && part.endsWith("`")) {
              return (
                <code key={i} className="rounded bg-black/10 px-1 py-0.5 font-mono text-[12px] dark:bg-white/10">
                  {part.slice(1, -1)}
                </code>
              );
            }
            return <span key={i}>{part}</span>;
          });
          if (bullet) {
            return (
              <div key={li} className="ml-1 flex gap-2">
                <span className="opacity-50">{bullet[2]}</span>
                <span>{inline}</span>
              </div>
            );
          }
          return (
            <span key={li}>
              {inline}
              {li < lines.length - 1 ? "\n" : null}
            </span>
          );
        })}
      </span>
    );
  });
}

function guessCompletedSteps(playbook: Playbook | null, messages: AiMessage[], toolTrace: string[]): Set<string> {
  const done = new Set<string>();
  if (!playbook) return done;
  const blob = `${messages.map((m) => m.content).join("\n")} ${toolTrace.join(" ")}`.toLowerCase();
  for (const step of playbook.steps) {
    const id = step.id;
    if (id === "repo" && /(github|gitlab|remote_url|dépôt|repo)/i.test(blob)) done.add(id);
    if (id === "runtime" && /(python|node|version)/i.test(blob)) done.add(id);
    if (id === "domain" && /(domaine|domain)/i.test(blob)) done.add(id);
    if (id === "database" && /(mysql|postgres|database|base de données)/i.test(blob)) done.add(id);
    if (id === "env" && /(env|variable)/i.test(blob)) done.add(id);
    if (id === "clone" && /(clone|cloned|git)/i.test(blob)) done.add(id);
    if (id === "app" && /(app_id|application créée|create_python|create_node)/i.test(blob)) done.add(id);
    if (id === "deps" && /(pip|npm install|dépendances|install_dependencies)/i.test(blob)) done.add(id);
    if (id === "start" && /(restart|running|démarr)/i.test(blob)) done.add(id);
    if (id === "logs" && /(log|get_deployment_logs)/i.test(blob)) done.add(id);
    if (id === "analyze" && /(analyze_deployment|ModuleNotFound|problème détecté)/i.test(blob)) done.add(id);
    if (id === "fix" && /(correction|confirm|install_dependencies|restart)/i.test(blob)) done.add(id);
    if (id === "status" && /check_application_status/.test(blob)) done.add(id);
    if (id === "web" && /check_web_server/.test(blob)) done.add(id);
    if (id === "install" && /wordpress/i.test(blob)) done.add(id);
    if (id === "ssl" && /ssl/i.test(blob)) done.add(id);
  }
  return done;
}

const WELCOME =
  "Salut ! Je suis **V-zone AI** — on peut discuter librement, comme avec ChatGPT.\n\n" +
  "Pose ta question, décris un bug, ou demande un plan de déploiement. " +
  "Quand une action sensible est nécessaire (logs live, restart, jail…), je te demanderai confirmation.";

export function AiDeploymentAssistant() {
  const location = useLocation();
  const pageCtx = useMemo(() => buildUiPageContext(location.pathname), [location.pathname]);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [localMessages, setLocalMessages] = useState<AiMessage[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [activePlaybookId, setActivePlaybookId] = useState<string | null>(null);
  const [toolNames, setToolNames] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const autoPageKey = useRef<string>("");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const qc = useQueryClient();

  const statusQuery = useQuery({
    queryKey: ["ai-status"],
    queryFn: () =>
      apiRequest<{
        provider: string;
        available: boolean;
        tools: { name: string; dangerous: boolean }[];
        playbooks: Playbook[];
        jail_commands: JailCommand[];
      }>("/ai/status/"),
    enabled: open,
    staleTime: 60_000,
  });

  const historyQuery = useQuery({
    queryKey: ["ai-conversations"],
    queryFn: () => apiRequest<ConversationSummary[]>("/ai/conversations/"),
    enabled: open && showHistory,
  });

  const playbooks = statusQuery.data?.playbooks || [];
  const jailCommands = statusQuery.data?.jail_commands || [];
  const activePlaybook = useMemo(
    () => playbooks.find((p) => p.id === activePlaybookId) || null,
    [playbooks, activePlaybookId],
  );
  const completed = useMemo(
    () => guessCompletedSteps(activePlaybook, localMessages, toolNames),
    [activePlaybook, localMessages, toolNames],
  );
  const progressPct = activePlaybook
    ? Math.round((completed.size / Math.max(activePlaybook.steps.length, 1)) * 100)
    : 0;

  const bootstrapConversation = useCallback(async (opts?: { title?: string; keepWelcome?: boolean }) => {
    const conv = await apiRequest<Conversation>("/ai/conversations/", {
      method: "POST",
      body: JSON.stringify({ title: opts?.title || "" }),
    });
    setConversationId(conv.id);
    setPending([]);
    setToolNames([]);
    setLocalMessages(
      opts?.keepWelcome === false
        ? []
        : [{ role: "assistant", content: WELCOME }],
    );
    void qc.invalidateQueries({ queryKey: ["ai-conversations"] });
    return conv.id;
  }, [qc]);

  useEffect(() => {
    if (!open || conversationId) return;
    let cancelled = false;
    void (async () => {
      try {
        await bootstrapConversation();
      } catch {
        if (!cancelled) {
          setLocalMessages([
            { role: "assistant", content: "Impossible de démarrer la conversation. Vérifiez votre session / API." },
          ]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, conversationId, bootstrapConversation]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [localMessages, pending, open]);

  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 120);
  }, [open, conversationId]);

  const sendMut = useMutation({
    mutationFn: async (payload: { text: string; convId: number }) => {
      return apiRequest<SendResult>(`/ai/conversations/${payload.convId}/messages/`, {
        method: "POST",
        body: JSON.stringify({
          message: payload.text,
          ui_context: {
            path: pageCtx.path,
            section: pageCtx.section,
            portal: pageCtx.portal,
          },
        }),
      });
    },
    onSuccess: (data) => {
      setPending(data.pending_actions || []);
      setSuggestions(data.suggestions || []);
      const names = (data.tool_trace || [])
        .map((t) => String(t?.name || ""))
        .filter(Boolean);
      if (names.length) setToolNames((prev) => [...prev, ...names]);
      // Effet "streaming" type ChatGPT (affichage progressif)
      const full = data.message.content || "";
      setStreamingText("");
      let i = 0;
      const step = Math.max(2, Math.floor(full.length / 40));
      const timer = window.setInterval(() => {
        i = Math.min(full.length, i + step);
        setStreamingText(full.slice(0, i));
        if (i >= full.length) {
          window.clearInterval(timer);
          setStreamingText(null);
          setLocalMessages((prev) => [...prev, data.message]);
        }
      }, 16);
      void qc.invalidateQueries({ queryKey: ["ai-conversations"] });
    },
  });

  const confirmMut = useMutation({
    mutationFn: (payload: { token: string; confirm: boolean }) =>
      apiRequest<{ ok?: boolean; cancelled?: boolean; result?: unknown }>("/ai/actions/confirm/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (data, vars) => {
      setPending((prev) => prev.filter((p) => p.token !== vars.token));
      const ok = Boolean(data.ok);
      const label = !vars.confirm
        ? "Action annulée."
        : ok
          ? "**Action exécutée.**\n\n```json\n" +
            JSON.stringify(data.result ?? {}, null, 2).slice(0, 1800) +
            "\n```"
          : "**Action échouée.** Vérifiez les logs ou reformulez.";
      setLocalMessages((prev) => [...prev, { role: "assistant", content: label }]);
      if (vars.confirm && ok) {
        setToolNames((prev) => [...prev, "confirmed_action"]);
      }
    },
  });

  async function ensureConv(): Promise<number | null> {
    if (conversationId) return conversationId;
    try {
      return await bootstrapConversation({ keepWelcome: false });
    } catch {
      return null;
    }
  }

  async function onSend(raw?: string, forcedConvId?: number) {
    const text = (raw ?? input).trim();
    if (!text || sendMut.isPending || streamingText !== null) return;
    if (raw === undefined) setInput("");
    setSuggestions([]);
    const convId = forcedConvId ?? (await ensureConv());
    if (!convId) return;
    setLocalMessages((prev) => [...prev, { role: "user", content: text }]);
    try {
      await sendMut.mutateAsync({ text, convId });
    } catch (err) {
      setStreamingText(null);
      setLocalMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Erreur : ${err instanceof Error ? err.message : "envoi impossible"}`,
        },
      ]);
    }
  }

  async function requestJailCommand(cmd: JailCommand) {
    const text =
      `Exécute la commande jail autorisée \`${cmd.id}\` (${cmd.label}) ` +
      (cmd.needs_app ? "sur mon application la plus récente. " : "") +
      "Demande ma confirmation avant d'exécuter.";
    await onSend(text);
  }

  // Suggestion douce selon la page (sans spammer le fil de conversation)
  useEffect(() => {
    if (!open) return;
    const key = pageCtx.path;
    if (autoPageKey.current === key) return;
    autoPageKey.current = key;
    const sectionsHint = new Set(["python", "node", "git", "terminal", "files", "domains", "databases"]);
    if (!sectionsHint.has(pageCtx.section)) return;
    setSuggestions((prev) => {
      const next = [pageCtx.auto_prompt, ...prev.filter((s) => s !== pageCtx.auto_prompt)];
      return next.slice(0, 4);
    });
  }, [open, pageCtx.path, pageCtx.section, pageCtx.auto_prompt]);

  async function loadConversation(id: number) {
    const detail = await apiRequest<Conversation>(`/ai/conversations/${id}/`);
    setConversationId(detail.id);
    const msgs = (detail.messages || []).filter((m) => m.role === "user" || m.role === "assistant");
    setLocalMessages(msgs.length ? msgs : [{ role: "assistant", content: WELCOME }]);
    setPending([]);
    setShowHistory(false);
  }

  async function startPlaybook(pb: Playbook) {
    setActivePlaybookId(pb.id);
    setToolNames([]);
    autoPageKey.current = "";
    const id = await bootstrapConversation({ title: pb.title, keepWelcome: false });
    setLocalMessages([
      {
        role: "assistant",
        content:
          `Playbook **${pb.title}** démarré.\n\n` +
          "Suivez la checklist (agrandir le panneau pour la vue détaillée). Je vais vous poser les infos manquantes.",
      },
    ]);
    await onSend(pb.prompt, id);
  }

  const panelWidth = expanded ? "min(920px,96vw)" : "min(440px,94vw)";
  const panelHeight = expanded ? "min(820px,92vh)" : "min(680px,88vh)";

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="group fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full bg-cp-navy px-4 py-3 text-sm font-medium text-white shadow-lg transition hover:bg-cp-navy-soft"
          aria-label="Ouvrir l'assistant IA"
        >
          <span className="relative flex h-8 w-8 items-center justify-center rounded-full bg-white/15">
            <Sparkles className="h-4 w-4" />
            {pending.length > 0 && (
              <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-cp-orange" />
            )}
          </span>
          <span className="hidden sm:inline">Assistant IA</span>
        </button>
      )}

      {open && (
        <div
          className="fixed bottom-3 right-3 z-50 flex flex-col overflow-hidden rounded-2xl border border-cp-border bg-cp-canvas shadow-2xl dark:bg-surface-dark sm:bottom-5 sm:right-5"
          style={{ width: panelWidth, height: panelHeight }}
          role="dialog"
          aria-label="V-zone AI Deployment Assistant"
        >
          <header className="flex items-center justify-between gap-2 border-b border-cp-border bg-cp-header px-3 py-2.5 text-white">
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15">
                <Bot className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold tracking-wide">AI Deployment Assistant</p>
                <p className="truncate text-[10px] text-white/75">
                  {statusQuery.data
                    ? `${statusQuery.data.provider}${statusQuery.data.available ? " · prêt" : " · mode local"}`
                    : "connexion…"}
                  {` · ${pageCtx.label}`}
                  {activePlaybook ? ` · ${activePlaybook.title}` : ""}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                className="rounded-lg p-1.5 hover:bg-white/15"
                title="Historique"
                onClick={() => setShowHistory((v) => !v)}
              >
                <History className="h-4 w-4" />
              </button>
              <button
                type="button"
                className="rounded-lg p-1.5 hover:bg-white/15"
                title="Nouvelle conversation"
                onClick={() => {
                  setActivePlaybookId(null);
                  setConversationId(null);
                  void bootstrapConversation();
                }}
              >
                <Plus className="h-4 w-4" />
              </button>
              <button
                type="button"
                className="rounded-lg p-1.5 hover:bg-white/15"
                title={expanded ? "Réduire" : "Agrandir"}
                onClick={() => setExpanded((v) => !v)}
              >
                {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
              </button>
              <button
                type="button"
                className="rounded-lg p-1.5 hover:bg-white/15"
                title="Fermer"
                onClick={() => setOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </header>

          <div className="flex min-h-0 flex-1">
            {showHistory && (
              <aside className="flex w-[160px] shrink-0 flex-col border-r border-cp-border bg-white/70 dark:bg-black/20 sm:w-[200px]">
                <p className="px-2.5 py-2 text-[10px] font-semibold uppercase tracking-wide text-cp-muted">
                  Conversations
                </p>
                <div className="flex-1 overflow-y-auto px-1.5 pb-2">
                  {(historyQuery.data || []).map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => void loadConversation(c.id)}
                      className={`mb-1 w-full rounded-lg px-2 py-1.5 text-left text-xs transition hover:bg-cp-link-soft ${
                        c.id === conversationId ? "bg-cp-link-soft text-cp-navy" : "text-cp-text"
                      }`}
                    >
                      <span className="line-clamp-2 font-medium">{c.title || `Chat #${c.id}`}</span>
                    </button>
                  ))}
                  {historyQuery.isLoading && (
                    <p className="px-2 text-[11px] text-cp-muted">Chargement…</p>
                  )}
                </div>
              </aside>
            )}

            <div className={`flex min-w-0 flex-1 flex-col ${expanded ? "sm:flex-row" : ""}`}>
              <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                <div className="flex items-start gap-2 border-b border-cp-border bg-cp-link-soft/40 px-3 py-2 dark:bg-white/5">
                  <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cp-navy" />
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-semibold text-cp-navy dark:text-white">
                      Page : {pageCtx.label}
                    </p>
                    <p className="truncate text-[10px] text-cp-muted">{pageCtx.need}</p>
                  </div>
                  <button
                    type="button"
                    className="shrink-0 rounded-full border border-cp-border bg-white px-2 py-0.5 text-[10px] font-medium hover:bg-cp-link-soft dark:bg-black/30"
                    disabled={sendMut.isPending}
                    onClick={() => void onSend(`Je suis sur la page ${pageCtx.label}. ${pageCtx.need}. Aide-moi.`)}
                  >
                    Continuer ici
                  </button>
                </div>

                {playbooks.length > 0 && (
                  <div className="flex gap-1.5 overflow-x-auto border-b border-cp-border px-2.5 py-2">
                    {playbooks.map((pb) => (
                      <button
                        key={pb.id}
                        type="button"
                        onClick={() => void startPlaybook(pb)}
                        className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
                          activePlaybookId === pb.id
                            ? "border-cp-navy bg-cp-navy text-white"
                            : "border-cp-border bg-white text-cp-text hover:border-cp-link/40 dark:bg-black/20"
                        }`}
                      >
                        {pb.id === "diagnose-logs" ? (
                          <span className="inline-flex items-center gap-1">
                            <Bug className="h-3 w-3" /> {pb.title}
                          </span>
                        ) : (
                          pb.title
                        )}
                      </button>
                    ))}
                  </div>
                )}

                {(pageCtx.section === "terminal" || pageCtx.section === "files" || pageCtx.section === "python" || pageCtx.section === "node") &&
                  jailCommands.length > 0 && (
                    <div className="flex gap-1.5 overflow-x-auto border-b border-cp-border px-2.5 py-1.5">
                      <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-cp-muted">
                        <Terminal className="h-3 w-3" /> Jail
                      </span>
                      {jailCommands.slice(0, 8).map((cmd) => (
                        <button
                          key={cmd.id}
                          type="button"
                          title={cmd.description}
                          disabled={sendMut.isPending}
                          onClick={() => void requestJailCommand(cmd)}
                          className="shrink-0 rounded-full border border-dashed border-cp-border bg-white/80 px-2 py-0.5 text-[10px] text-cp-text hover:border-cp-navy dark:bg-black/20"
                        >
                          {cmd.label}
                        </button>
                      ))}
                    </div>
                  )}

                <div className="flex-1 space-y-2.5 overflow-y-auto px-3 py-3 text-sm">
                  {localMessages.map((m, idx) => (
                    <div
                      key={m.id ?? idx}
                      className={
                        m.role === "user"
                          ? "ml-6 rounded-2xl rounded-br-md bg-cp-navy px-3.5 py-2.5 text-white shadow-sm"
                          : "mr-4 rounded-2xl rounded-bl-md border border-cp-border bg-white px-3.5 py-2.5 text-cp-text shadow-sm dark:bg-black/25 dark:text-white"
                      }
                    >
                      <div className="whitespace-pre-wrap leading-relaxed">{renderContent(m.content)}</div>
                      {m.role === "assistant" && (
                        <button
                          type="button"
                          className="mt-2 inline-flex items-center gap-1 text-[10px] text-cp-muted hover:text-cp-navy"
                          onClick={() => void navigator.clipboard.writeText(m.content)}
                        >
                          <Copy className="h-3 w-3" /> Copier
                        </button>
                      )}
                    </div>
                  ))}

                  {streamingText !== null && (
                    <div className="mr-4 rounded-2xl rounded-bl-md border border-cp-border bg-white px-3.5 py-2.5 text-cp-text shadow-sm dark:bg-black/25 dark:text-white">
                      <div className="whitespace-pre-wrap leading-relaxed">
                        {renderContent(streamingText)}
                        <span className="ml-0.5 inline-block h-4 w-1 animate-pulse bg-cp-navy align-middle" />
                      </div>
                    </div>
                  )}

                  {pending.map((p) => (
                    <div
                      key={p.token}
                      className="rounded-xl border border-amber-300/80 bg-gradient-to-br from-amber-50 to-orange-50 px-3.5 py-3 text-amber-950 shadow-sm dark:border-amber-700 dark:from-amber-950/50 dark:to-orange-950/30 dark:text-amber-50"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700 dark:text-amber-200">
                            Confirmation requise
                          </p>
                          <p className="mt-1 text-sm font-medium">{p.description || p.tool_name}</p>
                          <p className="mt-0.5 font-mono text-[11px] opacity-70">{p.tool_name}</p>
                        </div>
                        <ChevronRight className="mt-1 h-4 w-4 opacity-40" />
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 rounded-lg bg-cp-orange px-3 py-1.5 text-xs font-semibold text-white hover:bg-cp-orange-dark disabled:opacity-60"
                          disabled={confirmMut.isPending}
                          onClick={() => confirmMut.mutate({ token: p.token, confirm: true })}
                        >
                          <Check className="h-3.5 w-3.5" />
                          Exécuter
                        </button>
                        <button
                          type="button"
                          className="vz-btn-ghost !px-3 !py-1.5 text-xs"
                          disabled={confirmMut.isPending}
                          onClick={() => confirmMut.mutate({ token: p.token, confirm: false })}
                        >
                          Annuler
                        </button>
                      </div>
                    </div>
                  ))}

                  {sendMut.isPending && streamingText === null && (
                    <div className="flex items-center gap-2 text-xs text-cp-muted">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      V-zone AI réfléchit…
                    </div>
                  )}

                  {suggestions.length > 0 && !sendMut.isPending && streamingText === null && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {suggestions.map((s) => (
                        <button
                          key={s}
                          type="button"
                          className="rounded-full border border-cp-border bg-white px-2.5 py-1 text-left text-[11px] text-cp-text transition hover:border-cp-navy hover:bg-cp-link-soft dark:bg-black/20"
                          onClick={() => void onSend(s)}
                        >
                          {s.length > 72 ? `${s.slice(0, 72)}…` : s}
                        </button>
                      ))}
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>

                <div className="border-t border-cp-border bg-white/80 p-2.5 dark:bg-black/20">
                  <form
                    className="flex items-end gap-2"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void onSend();
                    }}
                  >
                    <textarea
                      ref={inputRef}
                      rows={1}
                      className="vz-input max-h-28 flex-1 resize-none !py-2.5 text-sm"
                      placeholder="Écris comme à ChatGPT… (Shift+Entrée = nouvelle ligne)"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void onSend();
                        }
                      }}
                      disabled={sendMut.isPending}
                    />
                    <button
                      type="submit"
                      className="vz-btn-primary !h-[42px] !px-3"
                      disabled={!input.trim() || sendMut.isPending}
                      aria-label="Envoyer"
                    >
                      <Send className="h-4 w-4" />
                    </button>
                  </form>
                  <p className="mt-1.5 px-0.5 text-[10px] text-cp-muted">
                    Tools contrôlés · conversation multi-tours · Entrée pour envoyer
                  </p>
                </div>
              </div>

              {expanded && activePlaybook && (
                <aside className="hidden w-[240px] shrink-0 flex-col border-l border-cp-border bg-white/60 p-3 dark:bg-black/20 sm:flex">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-cp-muted">Checklist</p>
                  <p className="mt-1 text-sm font-semibold text-cp-text dark:text-white">{activePlaybook.title}</p>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
                    <div
                      className="h-full rounded-full bg-cp-navy transition-all duration-500"
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                  <p className="mt-1 text-[11px] text-cp-muted">{progressPct}% complété</p>
                  <ol className="mt-3 space-y-2">
                    {activePlaybook.steps.map((step, i) => {
                      const ok = completed.has(step.id);
                      return (
                        <li key={step.id} className="flex items-start gap-2 text-xs">
                          <span
                            className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                              ok ? "bg-emerald-500 text-white" : "bg-black/10 text-cp-muted dark:bg-white/10"
                            }`}
                          >
                            {ok ? <Check className="h-3 w-3" /> : i + 1}
                          </span>
                          <span className={ok ? "text-cp-muted line-through" : "text-cp-text dark:text-white"}>
                            {step.label}
                          </span>
                        </li>
                      );
                    })}
                  </ol>
                </aside>
              )}
            </div>
          </div>

          {activePlaybook && !expanded && (
            <div className="border-t border-cp-border px-3 py-2">
              <div className="mb-1 flex items-center justify-between text-[10px] text-cp-muted">
                <span>{activePlaybook.title}</span>
                <span>{progressPct}%</span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
                <div className="h-full bg-cp-navy transition-all" style={{ width: `${progressPct}%` }} />
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
