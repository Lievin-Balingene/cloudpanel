/** Actions IA en attente d'approbation (Command Approval). */

export interface PendingAction {
  action_token?: string;
  token?: string;
  tool_name: string;
  description: string;
  params?: Record<string, unknown>;
  expires_at?: string;
  created_at?: string;
  conversation_id?: number;
  risk?: string;
  command_preview?: string;
}

export interface ToolTraceItem {
  name?: string;
  ok?: boolean;
  pending?: boolean;
  action_token?: string;
  summary?: {
    action_token?: string;
    tool_name?: string;
    pending_confirmation?: boolean;
  };
}

/** Jeton d'approbation — préfère `action_token` (non masqué par redaction). */
export function pendingActionToken(action: PendingAction): string {
  const raw = String(action.action_token || action.token || "").trim();
  if (!raw || raw.includes("REDACTED") || raw === "***") return "";
  return raw;
}

export function mergePendingActions(
  current: PendingAction[],
  incoming: PendingAction[],
): PendingAction[] {
  const map = new Map<string, PendingAction>();
  for (const item of current) {
    const t = pendingActionToken(item);
    if (t) map.set(t, item);
  }
  for (const item of incoming) {
    const t = pendingActionToken(item);
    if (t) map.set(t, { ...item, action_token: t, token: t });
  }
  return Array.from(map.values()).sort((a, b) => {
    const ta = a.created_at || a.expires_at || "";
    const tb = b.created_at || b.expires_at || "";
    return tb.localeCompare(ta);
  });
}

/** Reconstruit des actions pending depuis tool_trace si pending_actions est vide. */
export function pendingFromToolTrace(trace: ToolTraceItem[] | undefined): PendingAction[] {
  if (!trace?.length) return [];
  const out: PendingAction[] = [];
  for (const t of trace) {
    const token = String(
      t.action_token || t.summary?.action_token || "",
    ).trim();
    if (!token || token.includes("REDACTED")) continue;
    if (!(t.pending || t.summary?.pending_confirmation)) continue;
    const name = t.name || t.summary?.tool_name || "action";
    out.push({
      action_token: token,
      token,
      tool_name: name,
      description: `Approuver \`${name}\``,
      risk: "high",
      command_preview: name,
    });
  }
  return out;
}

/** Récupère un jeton d'approbation collé dans le texte assistant (JSON / message). */
export function pendingFromAssistantText(text: string): PendingAction | null {
  const raw = text || "";
  const m =
    raw.match(/"action_token"\s*:\s*"([^"]{16,})"/) ||
    raw.match(/action_token["']?\s*[:=]\s*["']([A-Za-z0-9_-]{16,})["']/i) ||
    raw.match(/ACTION NON EXÉCUTÉE[\s\S]{0,400}?([A-Za-z0-9_-]{32,})/);
  if (!m?.[1] || m[1].includes("REDACTED")) return null;
  const tool =
    raw.match(/"tool_name"\s*:\s*"([^"]+)"/)?.[1] ||
    raw.match(/`([a-z0-9_]+)` est en attente/)?.[1] ||
    "action";
  return {
    action_token: m[1],
    token: m[1],
    tool_name: tool,
    description: `Approuver \`${tool}\``,
    risk: "high",
    command_preview: tool,
  };
}

const APPROVE_RE =
  /^(oui|ok|okay|approuver|approve|valider|confirmer|vas-?y|go|lance|exécuter|executer|toi[-\s]?m[eê]me|fais[-\s]?le(\s+toi)?)\s*[.!]?\s*$/i;

/** True si le message utilisateur veut approuver l'action en attente. */
export function isApproveShortcut(text: string): boolean {
  const t = (text || "").trim();
  if (APPROVE_RE.test(t)) return true;
  const lower = t.toLowerCase();
  return (
    lower.includes("toi meme") ||
    lower.includes("toi-même") ||
    lower.includes("toi même") ||
    lower.includes("je ne veux pas") ||
    lower.includes("sans cliquer") ||
    lower.includes("fais le toi") ||
    lower.includes("execute maintenant") ||
    lower.includes("exécute maintenant")
  );
}

const REFUSE_RE = /^(non|refuser|annuler|cancel|refuse)\s*[.!]?$/i;

export function isRefuseShortcut(text: string): boolean {
  return REFUSE_RE.test((text || "").trim());
}
