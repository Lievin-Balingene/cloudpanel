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

const APPROVE_RE =
  /^(oui|ok|okay|approuver|approve|valider|confirmer|vas-?y|go|lance|exécuter|executer)\s*[.!]?$/i;

/** True si le message utilisateur veut approuver l'action en attente. */
export function isApproveShortcut(text: string): boolean {
  return APPROVE_RE.test((text || "").trim());
}

const REFUSE_RE = /^(non|refuser|annuler|cancel|refuse)\s*[.!]?$/i;

export function isRefuseShortcut(text: string): boolean {
  return REFUSE_RE.test((text || "").trim());
}
