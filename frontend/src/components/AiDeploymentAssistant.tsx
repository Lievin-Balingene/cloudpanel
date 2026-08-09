import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Bug,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  History,
  Loader2,
  MapPin,
  Maximize2,
  Minimize2,
  Plus,
  Rocket,
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

const STARTERS = [
  { label: "Vue du compte", prompt: "Montre la vue d'ensemble de mon compte" },
  { label: "Mes apps", prompt: "Liste moi mes applications Python et Node" },
  { label: "Mes domaines", prompt: "Liste mes domaines et le statut SSL" },
  { label: "Sites WordPress", prompt: "Liste mes sites WordPress" },
  { label: "Installer WordPress", prompt: "Crée un site WordPress sur wp.exemple.com" },
  { label: "Bases de données", prompt: "Liste mes bases de données" },
  { label: "Emails", prompt: "Liste mes boîtes mail" },
  { label: "Sauvegardes", prompt: "Liste mes sauvegardes" },
] as const;

const THINKING_PHRASES = [
  "Analyse de ta demande…",
  "Consultation du panneau…",
  "Préparation de la réponse…",
] as const;

function JsonBlock({ raw, lang }: { raw: string; lang?: string }) {
  const [open, setOpen] = useState(false);
  let pretty = raw.trim();
  let isJson = false;
  try {
    pretty = JSON.stringify(JSON.parse(raw), null, 2);
    isJson = true;
  } catch {
    /* keep raw */
  }
  const lines = pretty.split("\n").length;
  const collapsed = !open && (isJson || lines > 8);
  const shown = collapsed ? pretty.split("\n").slice(0, 6).join("\n") + (lines > 6 ? "\n…" : "") : pretty;

  return (
    <div className="vz-ai-codeblock my-2.5 overflow-hidden">
      <div className="vz-ai-codeblock-bar">
        <span className="font-mono text-[10px] uppercase tracking-wide opacity-70">
          {lang || (isJson ? "json" : "code")}
        </span>
        <div className="flex items-center gap-1">
          {(isJson || lines > 8) && (
            <button
              type="button"
              className="rounded px-1.5 py-0.5 text-[10px] font-medium hover:bg-white/10"
              onClick={() => setOpen((v) => !v)}
            >
              {open ? "Réduire" : "Tout voir"}
            </button>
          )}
        </div>
      </div>
      <pre className="vz-ai-code overflow-x-auto p-3 text-[11px] leading-relaxed">{shown}</pre>
    </div>
  );
}

function renderInline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|_[^_\n]+_)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-cp-navy dark:text-white">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="vz-ai-inline-code">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("_") && part.endsWith("_") && part.length > 2) {
      return (
        <em key={i} className="text-[12px] text-cp-muted not-italic opacity-80">
          {part.slice(1, -1)}
        </em>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

function renderContent(text: string) {
  const cleaned = text.replace(/\n*_\(Mode local\.\)_\s*$/i, "").trimEnd();
  const blocks = cleaned.split(/(```[\s\S]*?```)/g);
  return blocks.map((block, bi) => {
    if (block.startsWith("```") && block.endsWith("```")) {
      const match = block.match(/^```(\w*)\n?([\s\S]*)```$/);
      const lang = match?.[1] || "";
      const body = (match?.[2] ?? block.replace(/^```\w*\n?/, "").replace(/```$/, "")).replace(/\n$/, "");
      return <JsonBlock key={bi} raw={body} lang={lang} />;
    }

    const paragraphs = block.split(/\n{2,}/);
    return (
      <div key={bi} className="space-y-2.5">
        {paragraphs.map((para, pi) => {
          const lines = para.split("\n");
          const isList = lines.every((l) => !l.trim() || /^(\s*)([-*]|\d+\.)\s+/.test(l));
          if (isList && lines.some((l) => /^(\s*)([-*]|\d+\.)\s+/.test(l))) {
            return (
              <ul key={pi} className="vz-ai-list space-y-1.5">
                {lines.map((line, li) => {
                  const bullet = line.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
                  if (!bullet) {
                    return line.trim() ? (
                      <li key={li} className="list-none">
                        {renderInline(line)}
                      </li>
                    ) : null;
                  }
                  return (
                    <li key={li} className="flex gap-2">
                      <span className="mt-0.5 select-none text-[11px] text-cp-navy/50 dark:text-white/40">
                        {bullet[2] === "-" || bullet[2] === "*" ? "•" : bullet[2]}
                      </span>
                      <span className="min-w-0 flex-1 leading-relaxed">{renderInline(bullet[3])}</span>
                    </li>
                  );
                })}
              </ul>
            );
          }
          return (
            <p key={pi} className="leading-relaxed text-[13px] sm:text-[13.5px]">
              {lines.map((line, li) => (
                <span key={li}>
                  {renderInline(line)}
                  {li < lines.length - 1 ? <br /> : null}
                </span>
              ))}
            </p>
          );
        })}
      </div>
    );
  });
}

function ThinkingCard({ pageLabel }: { pageLabel: string }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => {
      setI((n) => (n + 1) % THINKING_PHRASES.length);
    }, 1800);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="vz-ai-msg flex items-center gap-2.5" aria-live="polite" aria-busy="true">
      <div className="vz-ai-avatar-think relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full">
        <span className="vz-ai-think-ring" aria-hidden />
        <Loader2 className="relative h-3.5 w-3.5 animate-spin text-cp-navy dark:text-white" />
      </div>
      <div className="vz-ai-thinking-inline min-w-0">
        <p className="truncate text-[13px] text-cp-text dark:text-white/90">
          <span className="font-medium">{THINKING_PHRASES[i]}</span>
          <span className="vz-ai-think-dots ml-1.5 inline-flex" aria-hidden>
            <i />
            <i />
            <i />
          </span>
        </p>
        <p className="truncate text-[10px] text-cp-muted">{pageLabel}</p>
      </div>
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div className="space-y-2 px-1.5" aria-hidden>
      {[0, 1, 2].map((n) => (
        <div key={n} className="rounded-xl px-2.5 py-2">
          <div className="vz-ai-shimmer h-2.5 w-[80%] rounded-full" />
        </div>
      ))}
    </div>
  );
}

function BootSkeleton() {
  return (
    <div className="flex flex-1 items-start gap-2.5 px-3 py-4" aria-busy="true">
      <div className="vz-ai-shimmer h-8 w-8 shrink-0 rounded-full" />
      <div className="min-w-0 flex-1 space-y-2 pt-1">
        <div className="vz-ai-shimmer h-2.5 w-[70%] rounded-full" />
        <div className="vz-ai-shimmer h-2.5 w-[45%] rounded-full" />
      </div>
    </div>
  );
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
  "Salut ! Je suis **V-zone AI** — assistant du panneau client.\n\n" +
  "Je peux **lister et piloter** apps, domaines, SSL, DB, email, fichiers, cron, " +
  "WordPress, FTP, backups, Git, Docker… Les actions sensibles demandent ta confirmation. " +
  "Mot de passe / 2FA : je guide seulement (pas d'exécution).";

function providerLabel(provider?: string, available?: boolean): { text: string; tone: "ok" | "warn" | "muted" } {
  if (!provider) return { text: "Connexion…", tone: "muted" };
  if (provider === "mock") return { text: "Mode local", tone: "warn" };
  if (available) return { text: `${provider} · prêt`, tone: "ok" };
  return { text: `${provider} · indisponible`, tone: "warn" };
}

export function AiDeploymentAssistant() {
  const location = useLocation();
  const pageCtx = useMemo(() => buildUiPageContext(location.pathname), [location.pathname]);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showGuides, setShowGuides] = useState(false);
  const [showJail, setShowJail] = useState(false);
  const [contextDismissed, setContextDismissed] = useState(false);
  const [mockHintDismissed, setMockHintDismissed] = useState(false);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [localMessages, setLocalMessages] = useState<AiMessage[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [activePlaybookId, setActivePlaybookId] = useState<string | null>(null);
  const [toolNames, setToolNames] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const autoPageKey = useRef<string>("");
  const streamTimer = useRef<number | null>(null);
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

  const bootstrapConversation = useCallback(
    async (opts?: { title?: string; keepWelcome?: boolean }) => {
      const conv = await apiRequest<Conversation>("/ai/conversations/", {
        method: "POST",
        body: JSON.stringify({ title: opts?.title || "" }),
      });
      setConversationId(conv.id);
      setPending([]);
      setToolNames([]);
      setSuggestions([]);
      setLocalMessages(opts?.keepWelcome === false ? [] : [{ role: "assistant", content: WELCOME }]);
      void qc.invalidateQueries({ queryKey: ["ai-conversations"] });
      return conv.id;
    },
    [qc],
  );

  useEffect(() => {
    if (!open || conversationId) return;
    let cancelled = false;
    void (async () => {
      try {
        await bootstrapConversation();
      } catch {
        if (!cancelled) {
          setLocalMessages([
            {
              role: "assistant",
              content: "Impossible de démarrer la conversation. Vérifiez votre session / API.",
            },
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
  }, [localMessages, pending, open, streamingText, suggestions]);

  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 120);
  }, [open, conversationId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showGuides) setShowGuides(false);
        else if (showHistory) setShowHistory(false);
        else setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, showGuides, showHistory]);

  useEffect(() => {
    return () => {
      if (streamTimer.current) window.clearInterval(streamTimer.current);
    };
  }, []);

  useEffect(() => {
    setContextDismissed(false);
  }, [pageCtx.path]);

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
      const names = (data.tool_trace || []).map((t) => String(t?.name || "")).filter(Boolean);
      if (names.length) setToolNames((prev) => [...prev, ...names]);
      const full = data.message.content || "";
      if (streamTimer.current) window.clearInterval(streamTimer.current);
      setStreamingText("");
      let i = 0;
      const step = Math.max(3, Math.floor(full.length / 35));
      streamTimer.current = window.setInterval(() => {
        i = Math.min(full.length, i + step);
        setStreamingText(full.slice(0, i));
        if (i >= full.length) {
          if (streamTimer.current) window.clearInterval(streamTimer.current);
          streamTimer.current = null;
          setStreamingText(null);
          setLocalMessages((prev) => [
            ...prev,
            {
              ...data.message,
              metadata: {
                ...(data.message.metadata || {}),
                tool_trace: data.tool_trace || [],
                provider: data.provider,
              },
            },
          ]);
        }
      }, 14);
      void qc.invalidateQueries({ queryKey: ["ai-conversations"] });
    },
  });

  const isBusy = sendMut.isPending || streamingText !== null;

  const confirmMut = useMutation({
    mutationFn: (payload: { token: string; confirm: boolean }) =>
      apiRequest<{
        ok?: boolean;
        cancelled?: boolean;
        result?: unknown;
        pending_actions?: PendingAction[];
      }>("/ai/actions/confirm/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (data, vars) => {
      const followUps = data.pending_actions || [];
      setPending((prev) => [
        ...prev.filter((p) => p.token !== vars.token),
        ...followUps,
      ]);
      const ok = Boolean(data.ok);
      let label: string;
      if (!vars.confirm) {
        label = "Action annulée.";
      } else if (ok) {
        label =
          "**Action exécutée avec succès.**" +
          (followUps.length
            ? "\n\nProchaine étape prête — confirme **Exécuter** ci-dessous."
            : "");
        const result = data.result;
        if (result && typeof result === "object") {
          const compact = JSON.stringify(result, null, 2).slice(0, 900);
          label += `\n\n\`\`\`json\n${compact}\n\`\`\``;
        }
      } else {
        label = "**Action échouée.** Vérifiez les logs ou reformulez.";
      }
      setLocalMessages((prev) => [...prev, { role: "assistant", content: label }]);
      if (vars.confirm && ok) setToolNames((prev) => [...prev, "confirmed_action"]);
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
    if (!text || isBusy) return;
    if (raw === undefined) setInput("");
    setSuggestions([]);
    setShowGuides(false);
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
    setShowGuides(false);
    autoPageKey.current = "";
    const id = await bootstrapConversation({ title: pb.title, keepWelcome: false });
    setLocalMessages([
      {
        role: "assistant",
        content:
          `Guide **${pb.title}** démarré.\n\n` +
          "Je vais te poser les infos manquantes. Agrandis le panneau pour voir la checklist.",
      },
    ]);
    await onSend(pb.prompt, id);
  }

  function autoResize() {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }

  async function copyText(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(key);
      window.setTimeout(() => setCopiedId(null), 1500);
    } catch {
      /* ignore */
    }
  }

  const userMsgCount = localMessages.filter((m) => m.role === "user").length;
  const showEmptyStarters = userMsgCount === 0 && !isBusy && pending.length === 0;
  const status = providerLabel(statusQuery.data?.provider, statusQuery.data?.available);
  const showJailBar =
    showJail &&
    jailCommands.length > 0 &&
    ["terminal", "files", "python", "node"].includes(pageCtx.section);

  const panelWidth = expanded ? "min(960px,96vw)" : "min(420px,94vw)";
  const panelHeight = expanded ? "min(860px,94vh)" : "min(640px,86vh)";

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="vz-ai-fab group fixed bottom-5 right-5 z-40 inline-flex items-center gap-2.5 rounded-full bg-cp-navy pl-2 pr-4 py-2 text-sm font-medium text-white shadow-lg transition hover:bg-cp-navy-soft hover:shadow-xl"
          aria-label="Ouvrir V-zone AI"
        >
          <span className="relative flex h-9 w-9 items-center justify-center rounded-full bg-white/15">
            <span className="vz-ai-fab-ring" aria-hidden />
            <span className="vz-ai-fab-glow" aria-hidden />
            <Sparkles className="relative h-4 w-4 transition group-hover:scale-110" />
            {pending.length > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-cp-orange px-1 text-[9px] font-bold">
                {pending.length}
              </span>
            )}
          </span>
          <span className="hidden flex-col items-start leading-tight sm:flex">
            <span>V-zone AI</span>
            <span className="text-[10px] font-normal text-white/70">Assistant intelligent</span>
          </span>
        </button>
      )}

      {open && (
        <>
          <button
            type="button"
            className={`fixed inset-0 z-40 bg-black/25 backdrop-blur-[2px] transition ${
              expanded ? "opacity-100" : "opacity-0 pointer-events-none sm:opacity-0"
            }`}
            aria-label="Fermer l'arrière-plan"
            onClick={() => (expanded ? setExpanded(false) : setOpen(false))}
          />

          <div
            className="vz-ai-panel fixed bottom-3 right-3 z-50 flex flex-col overflow-hidden sm:bottom-5 sm:right-5"
            style={{ width: panelWidth, height: panelHeight }}
            role="dialog"
            aria-label="V-zone AI"
          >
            <header className="vz-ai-header flex items-center justify-between gap-2 px-3 py-3 text-white">
              <div className="flex min-w-0 items-center gap-2.5">
                <div className="vz-ai-header-avatar relative flex h-10 w-10 items-center justify-center rounded-2xl">
                  <Bot className="relative z-[1] h-[18px] w-[18px]" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold tracking-wide">V-zone AI</p>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                    <span
                      className={`vz-ai-pill ${
                        status.tone === "ok"
                          ? "vz-ai-pill-ok"
                          : status.tone === "warn"
                            ? "vz-ai-pill-warn"
                            : "vz-ai-pill-muted"
                      }`}
                    >
                      <span className="vz-ai-dot" />
                      {status.text}
                    </span>
                    <span className="truncate text-[10px] text-white/65">{pageCtx.label}</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-0.5">
                <IconBtn title="Historique" active={showHistory} onClick={() => setShowHistory((v) => !v)}>
                  <History className="h-4 w-4" />
                </IconBtn>
                <IconBtn
                  title="Nouvelle conversation"
                  onClick={() => {
                    setActivePlaybookId(null);
                    setConversationId(null);
                    void bootstrapConversation();
                  }}
                >
                  <Plus className="h-4 w-4" />
                </IconBtn>
                <IconBtn title={expanded ? "Réduire" : "Agrandir"} onClick={() => setExpanded((v) => !v)}>
                  {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                </IconBtn>
                <IconBtn title="Fermer (Échap)" onClick={() => setOpen(false)}>
                  <X className="h-4 w-4" />
                </IconBtn>
              </div>
            </header>

            <div className="flex min-h-0 flex-1">
              {showHistory && (
                <aside className="vz-ai-aside flex w-[168px] shrink-0 flex-col sm:w-[210px]">
                  <p className="px-2.5 py-2 text-[10px] font-semibold uppercase tracking-wider text-cp-muted">
                    Historique
                  </p>
                  <div className="flex-1 overflow-y-auto px-1.5 pb-2">
                    {(historyQuery.data || []).map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => void loadConversation(c.id)}
                        className={`mb-1 w-full rounded-xl px-2.5 py-2 text-left text-xs transition ${
                          c.id === conversationId
                            ? "bg-cp-navy/10 text-cp-navy ring-1 ring-cp-navy/20 dark:bg-white/10 dark:text-white"
                            : "text-cp-text hover:bg-black/[0.04] dark:hover:bg-white/5"
                        }`}
                      >
                        <span className="line-clamp-2 font-medium">{c.title || `Chat #${c.id}`}</span>
                        {c.message_count != null && (
                          <span className="mt-0.5 block text-[10px] text-cp-muted">{c.message_count} msg</span>
                        )}
                      </button>
                    ))}
                    {historyQuery.isLoading && <HistorySkeleton />}
                    {!historyQuery.isLoading && (historyQuery.data || []).length === 0 && (
                      <p className="px-2 text-[11px] text-cp-muted">Aucune conversation.</p>
                    )}
                  </div>
                </aside>
              )}

              <div className={`flex min-w-0 flex-1 flex-col ${expanded ? "sm:flex-row" : ""}`}>
                <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                  {!contextDismissed && (
                    <div className="flex items-center gap-2 border-b border-cp-border/80 bg-gradient-to-r from-cp-link-soft/50 to-transparent px-3 py-2 dark:from-white/[0.06]">
                      <MapPin className="h-3.5 w-3.5 shrink-0 text-cp-navy dark:text-cp-link" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[11px] font-semibold text-cp-navy dark:text-white">
                          {pageCtx.label}
                        </p>
                        <p className="truncate text-[10px] text-cp-muted">{pageCtx.need}</p>
                      </div>
                      <button
                        type="button"
                        className="shrink-0 rounded-full bg-cp-navy px-2.5 py-1 text-[10px] font-semibold text-white hover:bg-cp-navy-soft disabled:opacity-50"
                        disabled={isBusy}
                        onClick={() =>
                          void onSend(`Je suis sur la page ${pageCtx.label}. ${pageCtx.need}. Aide-moi.`)
                        }
                      >
                        Continuer ici
                      </button>
                      <button
                        type="button"
                        className="rounded p-1 text-cp-muted hover:bg-black/5 hover:text-cp-text dark:hover:bg-white/10"
                        title="Masquer"
                        onClick={() => setContextDismissed(true)}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}

                  {statusQuery.data?.provider === "mock" && !mockHintDismissed && (
                    <div className="flex items-start gap-2 border-b border-amber-200/80 bg-amber-50/90 px-3 py-1.5 text-[10px] text-amber-900 dark:border-amber-800/50 dark:bg-amber-950/40 dark:text-amber-100">
                      <p className="flex-1 leading-snug">
                        Mode local actif — réponses sans LLM distant. Sur petit VPS :{" "}
                        <code className="rounded bg-black/10 px-1">ollama pull llama3.2:1b</code>
                      </p>
                      <button
                        type="button"
                        className="shrink-0 rounded p-0.5 hover:bg-amber-200/50"
                        onClick={() => setMockHintDismissed(true)}
                        aria-label="Fermer l'astuce"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  )}

                  <div className="flex items-center gap-1.5 border-b border-cp-border/70 px-2.5 py-1.5">
                    <button
                      type="button"
                      onClick={() => setShowGuides((v) => !v)}
                      className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium transition ${
                        showGuides
                          ? "bg-cp-navy text-white"
                          : "text-cp-text hover:bg-black/[0.04] dark:hover:bg-white/5"
                      }`}
                    >
                      <Rocket className="h-3 w-3" />
                      Guides
                      <ChevronDown className={`h-3 w-3 transition ${showGuides ? "rotate-180" : ""}`} />
                    </button>
                    {jailCommands.length > 0 &&
                      ["terminal", "files", "python", "node"].includes(pageCtx.section) && (
                        <button
                          type="button"
                          onClick={() => setShowJail((v) => !v)}
                          className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium transition ${
                            showJail
                              ? "bg-cp-navy text-white"
                              : "text-cp-text hover:bg-black/[0.04] dark:hover:bg-white/5"
                          }`}
                        >
                          <Terminal className="h-3 w-3" />
                          Jail
                        </button>
                      )}
                    {activePlaybook && (
                      <span className="ml-auto truncate text-[10px] text-cp-muted">{activePlaybook.title}</span>
                    )}
                  </div>

                  {showGuides && playbooks.length > 0 && (
                    <div className="grid grid-cols-1 gap-1.5 border-b border-cp-border bg-cp-canvas/80 p-2.5 dark:bg-black/20 sm:grid-cols-2">
                      {playbooks.map((pb) => (
                        <button
                          key={pb.id}
                          type="button"
                          onClick={() => void startPlaybook(pb)}
                          className={`rounded-xl border px-3 py-2 text-left transition hover:border-cp-navy/40 hover:bg-white dark:hover:bg-white/5 ${
                            activePlaybookId === pb.id
                              ? "border-cp-navy bg-white shadow-sm dark:bg-white/10"
                              : "border-cp-border/80 bg-white/60 dark:bg-black/20"
                          }`}
                        >
                          <span className="flex items-center gap-1.5 text-[12px] font-semibold text-cp-text dark:text-white">
                            {pb.id === "diagnose-logs" ? <Bug className="h-3.5 w-3.5" /> : <Rocket className="h-3.5 w-3.5" />}
                            {pb.title}
                          </span>
                          <span className="mt-0.5 block text-[10px] text-cp-muted">{pb.steps.length} étapes</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {showJailBar && (
                    <div className="flex gap-1.5 overflow-x-auto border-b border-cp-border px-2.5 py-1.5">
                      {jailCommands.slice(0, 10).map((cmd) => (
                        <button
                          key={cmd.id}
                          type="button"
                          title={cmd.description}
                          disabled={isBusy}
                          onClick={() => void requestJailCommand(cmd)}
                          className="shrink-0 rounded-full border border-dashed border-cp-border bg-white/80 px-2.5 py-1 text-[10px] text-cp-text hover:border-cp-navy dark:bg-black/20"
                        >
                          {cmd.label}
                        </button>
                      ))}
                    </div>
                  )}

                  <div className="vz-ai-thread flex-1 space-y-3.5 overflow-y-auto px-3 py-3 text-sm">
                    {!conversationId && localMessages.length === 0 ? (
                      <BootSkeleton />
                    ) : null}
                    {localMessages.map((m, idx) => {
                      const isUser = m.role === "user";
                      const key = String(m.id ?? `m-${idx}`);
                      const tools = Array.isArray(m.metadata?.tool_trace)
                        ? (m.metadata?.tool_trace as { name?: string; ok?: boolean }[])
                        : [];
                      return (
                        <div
                          key={key}
                          className={`vz-ai-msg flex gap-2.5 ${isUser ? "flex-row-reverse" : "flex-row"}`}
                        >
                          {!isUser && (
                            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cp-navy to-cp-navy-soft text-white shadow-sm">
                              <Bot className="h-3.5 w-3.5" />
                            </div>
                          )}
                          <div className={`min-w-0 max-w-[88%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
                            <div className={isUser ? "vz-ai-bubble-user" : "vz-ai-bubble-bot"}>
                              {!isUser && (
                                <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-cp-navy/55 dark:text-white/45">
                                  Assistant
                                </p>
                              )}
                              <div className={isUser ? "whitespace-pre-wrap leading-relaxed" : ""}>
                                {isUser ? m.content : renderContent(m.content)}
                              </div>
                            </div>
                            {!isUser && (
                              <div className="mt-1.5 flex flex-wrap items-center gap-1.5 px-1">
                                {tools.slice(0, 5).map((t, ti) =>
                                  t.name ? (
                                    <span
                                      key={`${t.name}-${ti}`}
                                      className={`vz-ai-toolchip ${t.ok === false ? "vz-ai-toolchip-err" : "vz-ai-toolchip-ok"}`}
                                    >
                                      {t.ok === false ? "✕" : "✓"} {t.name}
                                    </span>
                                  ) : null,
                                )}
                                <button
                                  type="button"
                                  className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] text-cp-muted transition hover:bg-black/[0.04] hover:text-cp-navy dark:hover:bg-white/10"
                                  onClick={() => void copyText(key, m.content)}
                                >
                                  {copiedId === key ? (
                                    <>
                                      <Check className="h-3 w-3 text-emerald-500" /> Copié
                                    </>
                                  ) : (
                                    <>
                                      <Copy className="h-3 w-3" /> Copier
                                    </>
                                  )}
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}

                    {showEmptyStarters && (
                      <div className="vz-ai-starters grid grid-cols-1 gap-2 pt-1 sm:grid-cols-2">
                        {STARTERS.map((s, i) => (
                          <button
                            key={s.label}
                            type="button"
                            disabled={isBusy}
                            onClick={() => void onSend(s.prompt)}
                            className="vz-ai-starter"
                            style={{ animationDelay: `${0.05 + i * 0.04}s` }}
                          >
                            <span className="block text-[12px] font-semibold text-cp-navy dark:text-white">
                              {s.label}
                            </span>
                            <span className="mt-0.5 block text-[10px] text-cp-muted line-clamp-2">{s.prompt}</span>
                          </button>
                        ))}
                      </div>
                    )}

                    {streamingText !== null && (
                      <div className="vz-ai-msg flex gap-2.5">
                        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cp-navy to-cp-navy-soft text-white shadow-sm">
                          <Bot className="h-3.5 w-3.5" />
                        </div>
                        <div className="vz-ai-bubble-bot max-w-[88%]">
                          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-cp-navy/55 dark:text-white/45">
                            Assistant
                          </p>
                          <div>
                            {renderContent(streamingText)}
                            <span className="vz-ai-caret ml-0.5 inline-block align-middle" />
                          </div>
                        </div>
                      </div>
                    )}

                    {pending.map((p) => (
                      <div key={p.token} className="vz-ai-confirm mx-1">
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
                      <ThinkingCard pageLabel={pageCtx.label} />
                    )}

                    {suggestions.length > 0 && !isBusy && (
                      <div className="flex flex-wrap gap-1.5 pt-0.5">
                        {suggestions.map((s) => (
                          <button
                            key={s}
                            type="button"
                            className="rounded-full border border-cp-border bg-white/90 px-2.5 py-1 text-left text-[11px] text-cp-text shadow-sm transition hover:border-cp-navy/40 hover:bg-cp-link-soft dark:bg-black/20"
                            onClick={() => void onSend(s)}
                          >
                            {s.length > 64 ? `${s.slice(0, 64)}…` : s}
                          </button>
                        ))}
                      </div>
                    )}
                    <div ref={bottomRef} />
                  </div>

                  <div className="vz-ai-composer border-t border-cp-border/80 p-2.5">
                    <form
                      className="flex items-end gap-2"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void onSend();
                      }}
                    >
                      <div className="relative flex-1">
                        <textarea
                          ref={inputRef}
                          rows={1}
                          className="vz-ai-input max-h-[120px] min-h-[46px] w-full resize-none rounded-2xl px-3.5 py-3 text-sm leading-snug"
                          placeholder="Écrire un message… (Entrée pour envoyer)"
                          value={input}
                          onChange={(e) => {
                            setInput(e.target.value);
                            autoResize();
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey) {
                              e.preventDefault();
                              void onSend();
                            }
                          }}
                          disabled={sendMut.isPending}
                        />
                      </div>
                      <button
                        type="submit"
                        className="vz-ai-send inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-white disabled:cursor-not-allowed disabled:opacity-40"
                        disabled={!input.trim() || isBusy}
                        aria-label="Envoyer"
                      >
                        {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                      </button>
                    </form>
                    <p className="mt-1.5 px-0.5 text-[10px] text-cp-muted">
                      Shift+Entrée = ligne · Échap = fermer · actions sensibles = confirmation
                    </p>
                  </div>
                </div>

                {expanded && activePlaybook && (
                  <aside className="vz-ai-aside hidden w-[248px] shrink-0 flex-col border-l border-cp-border p-3 sm:flex">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-cp-muted">Checklist</p>
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
        </>
      )}
    </>
  );
}

function IconBtn({
  children,
  title,
  onClick,
  active,
}: {
  children: ReactNode;
  title: string;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      className={`rounded-lg p-1.5 transition hover:bg-white/15 ${active ? "bg-white/20" : ""}`}
      title={title}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
