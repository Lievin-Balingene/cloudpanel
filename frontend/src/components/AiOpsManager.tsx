import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  Check,
  Database,
  FileWarning,
  Globe,
  Mail,
  RefreshCw,
  Shield,
  Terminal,
  X,
  Zap,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { pendingActionToken, type PendingAction } from "@/lib/aiPending";
import { EmptyState, PageHeader } from "@/components/ui/PageChrome";

const OPS = [
  {
    id: "diagnosis",
    icon: Activity,
    title: "Server Diagnosis",
    prompt:
      "Fais un diagnostic serveur : charge CPU/RAM, services critiques, alertes récentes. Résume les risques et propose des actions confirmables uniquement.",
  },
  {
    id: "errors",
    icon: FileWarning,
    title: "Error Analysis",
    prompt:
      "Analyse les erreurs récentes du panneau et des services (nginx/OLS, PHP, mail). Explique les causes probables et propose des correctifs avec confirmation.",
  },
  {
    id: "logs",
    icon: Terminal,
    title: "Log Analysis",
    prompt:
      "Aide-moi à analyser les logs système utiles (auth, web, mail). Indique ce qui est anormal et quelles commandes jail ou actions panel confirmer.",
  },
  {
    id: "security",
    icon: Shield,
    title: "Security Analysis",
    prompt:
      "Analyse sécurité : Fail2Ban, règles firewall, SSL expirants, politique mots de passe. Liste les findings et actions à approuver.",
  },
  {
    id: "perf",
    icon: Zap,
    title: "Performance Optimization",
    prompt:
      "Propose des optimisations performance (PHP OPcache, compression, quotas, process). N'exécute rien sans confirmation.",
  },
  {
    id: "dns",
    icon: Globe,
    title: "DNS Troubleshooter",
    prompt:
      "Aide au dépannage DNS : zones, enregistrements A/MX, propagation. Propose corrections avec confirmation.",
  },
  {
    id: "email",
    icon: Mail,
    title: "Email Troubleshooter",
    prompt:
      "Dépannage e-mail : SPF/DKIM/DMARC, file d'attente, livraison. Propose des actions confirmables.",
  },
  {
    id: "db",
    icon: Database,
    title: "Database Assistant",
    prompt:
      "Assistant bases de données : état MySQL/MariaDB, droits, réparations. Toute modification nécessite mon approbation.",
  },
] as const;

const riskStyle: Record<string, string> = {
  critical: "bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-200",
  high: "bg-amber-100 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200",
  medium: "bg-sky-100 text-sky-900 dark:bg-sky-950/40 dark:text-sky-200",
  low: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200",
};

function openAssistantWithPrompt(prompt: string) {
  window.dispatchEvent(
    new CustomEvent("vzone-ai-open", { detail: { prompt, autoSend: true } }),
  );
}

export function AiOpsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["ai-pending-actions"],
    queryFn: () =>
      apiRequest<{ pending_actions: PendingAction[]; count: number }>("/ai/actions/pending/"),
    refetchInterval: 5000,
  });

  const confirmMut = useMutation({
    mutationFn: (payload: { token: string; confirm: boolean }) =>
      apiRequest<{
        ok?: boolean;
        cancelled?: boolean;
        error?: string;
        pending_actions?: PendingAction[];
      }>("/ai/actions/confirm/", {
        method: "POST",
        body: JSON.stringify(payload),
        retry: false,
      }),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ["ai-pending-actions"] });
      if (data && data.ok === false && data.error) {
        window.alert(`Action échouée : ${data.error}`);
      }
    },
    onError: (err: Error) => {
      window.alert(err.message || "Confirmation impossible");
      void qc.invalidateQueries({ queryKey: ["ai-pending-actions"] });
    },
  });

  const pending = data?.pending_actions || [];

  return (
    <div className="space-y-4">
      <PageHeader
        title={title}
        subtitle="AI Assistant · diagnostic · Command Approval (Approuver / Refuser)"
        stats={[
          { label: "En attente", value: data?.count ?? pending.length },
          { label: "Playbooks", value: OPS.length },
        ]}
        actions={
          <button
            type="button"
            className="vz-btn-ghost inline-flex items-center gap-1.5 text-xs"
            onClick={() => void refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            Actualiser
          </button>
        }
      />

      <section className="vz-panel p-4">
        <div className="mb-3 flex items-center gap-2">
          <Bot className="h-4 w-4 text-cp-navy dark:text-white/70" />
          <h2 className="text-sm font-semibold">AI Operations</h2>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {OPS.map((op) => {
            const Icon = op.icon;
            return (
              <button
                key={op.id}
                type="button"
                onClick={() => openAssistantWithPrompt(op.prompt)}
                className="group rounded-xl border border-cp-border/80 bg-cp-canvas/40 p-3 text-left transition hover:border-cp-navy/40 hover:bg-white dark:hover:bg-white/5"
              >
                <Icon className="mb-2 h-4 w-4 text-cp-navy opacity-70 group-hover:opacity-100 dark:text-white/70" />
                <p className="text-sm font-medium">{op.title}</p>
                <p className="mt-1 text-[11px] leading-snug text-cp-muted">
                  Ouvre l’assistant avec un brief ciblé — aucune exécution auto.
                </p>
              </button>
            );
          })}
        </div>
      </section>

      <section className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border/70 px-4 py-3">
          <h2 className="text-sm font-semibold">AI Command Approval</h2>
          <p className="mt-0.5 text-xs text-cp-muted">
            Commande proposée → Explication → Risque → Approuver / Refuser
          </p>
        </div>

        {isLoading ? (
          <p className="px-4 py-6 text-sm text-cp-muted">Chargement…</p>
        ) : pending.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Shield className="h-8 w-8" />}
              message="Aucune commande en attente. L’IA proposera ici les actions sensibles."
            />
          </div>
        ) : (
          <ul className="divide-y divide-cp-border/60">
            {pending.map((p) => {
              const token = pendingActionToken(p);
              const risk = (p.risk || "medium").toLowerCase();
              return (
                <li key={token || p.tool_name} className="px-4 py-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                            riskStyle[risk] || riskStyle.medium
                          }`}
                        >
                          Risque {risk}
                        </span>
                        <span className="font-mono text-[11px] text-cp-muted">{p.tool_name}</span>
                      </div>
                      <p className="mt-1.5 text-sm font-medium">{p.description}</p>
                      <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-950/90 px-3 py-2 font-mono text-[11px] text-emerald-300 dark:bg-black/60">
                        {p.command_preview || p.tool_name}
                      </pre>
                      {p.expires_at && (
                        <p className="mt-1.5 text-[10px] text-cp-muted">
                          Expire : {new Date(p.expires_at).toLocaleString("fr-FR")}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded-lg bg-cp-orange px-3 py-1.5 text-xs font-semibold text-white hover:bg-cp-orange-dark disabled:opacity-60"
                        disabled={confirmMut.isPending || !token}
                        onClick={() => confirmMut.mutate({ token, confirm: true })}
                      >
                        <Check className="h-3.5 w-3.5" />
                        Approuver
                      </button>
                      <button
                        type="button"
                        className="vz-btn-ghost inline-flex items-center gap-1 !px-3 !py-1.5 text-xs"
                        disabled={confirmMut.isPending || !token}
                        onClick={() => confirmMut.mutate({ token, confirm: false })}
                      >
                        <X className="h-3.5 w-3.5" />
                        Refuser
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
