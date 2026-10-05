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

/** Jeton d'approbation — préfère `action_token` (non masqué par redaction). */
export function pendingActionToken(action: PendingAction): string {
  return String(action.action_token || action.token || "").trim();
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
    if (t) map.set(t, item);
  }
  return Array.from(map.values()).sort((a, b) => {
    const ta = a.created_at || a.expires_at || "";
    const tb = b.created_at || b.expires_at || "";
    return tb.localeCompare(ta);
  });
}
