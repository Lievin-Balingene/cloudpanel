import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { MailWarning, ShieldCheck } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageChrome";
import { useState } from "react";

interface SmtpRestrictionsStatus {
  enabled: boolean;
  disabled: boolean;
  message: string;
  description: string;
  ports: number[];
  allowed_users: string[];
  iptables_live?: boolean;
  mock?: boolean;
  provision_mode?: string;
  detail?: string;
  tweak_key?: string;
}

export function SmtpRestrictionsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["smtp-restrictions"],
    queryFn: () => apiRequest<SmtpRestrictionsStatus>("/security/smtp-restrictions/"),
  });

  const toggle = useMutation({
    mutationFn: (enabled: boolean) =>
      apiRequest<SmtpRestrictionsStatus>("/security/smtp-restrictions/", {
        method: "POST",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: (payload) => {
      setError(null);
      setOkMsg(
        payload.enabled
          ? "SMTP Restrictions activées."
          : "SMTP Restrictions désactivées.",
      );
      void qc.invalidateQueries({ queryKey: ["smtp-restrictions"] });
      void qc.invalidateQueries({ queryKey: ["tweak-settings"] });
    },
    onError: (err: Error) => {
      setOkMsg(null);
      setError(err.message);
    },
  });

  const enabled = Boolean(data?.enabled);

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Security Center · Empêche le by-pass du serveur mail (anti-spam)"
        stats={[
          { label: "État", value: isLoading ? "…" : enabled ? "Activé" : "Désactivé" },
          { label: "Port", value: (data?.ports || [25]).join(", ") },
        ]}
      />

      <nav className="text-xs text-cp-muted">
        <Link to="/whm" className="text-cp-link hover:underline">
          Home
        </Link>
        <span className="mx-1.5">/</span>
        <Link to="/whm/security" className="text-cp-link hover:underline">
          Security Center
        </Link>
        <span className="mx-1.5">/</span>
        <span className="text-cp-navy dark:text-white">SMTP Restrictions</span>
      </nav>

      {(error || okMsg) && (
        <p
          role="status"
          className={`rounded-lg border px-3 py-2 text-sm ${
            error
              ? "border-red-200 bg-red-50 text-cp-danger"
              : "border-emerald-200 bg-emerald-50 text-emerald-800"
          }`}
        >
          {error || okMsg}
        </p>
      )}

      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border bg-cp-canvas/60 px-4 py-2 text-xs font-bold uppercase tracking-wide text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          Documentation
        </div>
        <div className="space-y-3 p-4 text-sm leading-relaxed text-cp-text">
          <p>
            {data?.description ||
              "This feature prevents users from bypassing the mail server to send mail, a common practice used by spammers. It will allow only the MTA, mailman, and root to connect to remote SMTP servers."}
          </p>
          <p className="text-cp-muted">
            This control is also adjustable in{" "}
            <Link to="/whm/tweak-settings" className="text-cp-link hover:underline">
              Tweak Settings
            </Link>
            .
          </p>
          {!!data?.allowed_users?.length && (
            <p className="text-xs text-cp-muted">
              UIDs autorisés :{" "}
              <code className="font-mono text-cp-navy dark:text-white">
                {data.allowed_users.join(", ")}
              </code>
              {" · "}ports{" "}
              <code className="font-mono">{(data.ports || [25]).join(", ")}</code>
            </p>
          )}
        </div>
      </div>

      <div className="vz-panel p-5">
        {isLoading ? (
          <p className="text-sm text-cp-muted">Chargement…</p>
        ) : (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              {enabled ? (
                <ShieldCheck className="mt-0.5 h-8 w-8 shrink-0 text-emerald-600" />
              ) : (
                <MailWarning className="mt-0.5 h-8 w-8 shrink-0 text-amber-600" />
              )}
              <div>
                <p className="text-base font-semibold text-cp-navy dark:text-white">
                  {data?.message ||
                    (enabled
                      ? "The SMTP restriction is enabled."
                      : "The SMTP restriction is disabled.")}
                </p>
                <p className="mt-1 text-xs text-cp-muted">
                  {data?.mock
                    ? "Mode mock (pas d’iptables sur cet hôte)."
                    : data?.iptables_live
                      ? "Règles iptables OUTPUT actives."
                      : "État fichier — activez pour appliquer iptables."}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {enabled ? (
                <button
                  type="button"
                  className="vz-btn-ghost"
                  disabled={toggle.isPending}
                  onClick={() => toggle.mutate(false)}
                >
                  {toggle.isPending ? "…" : "Disable"}
                </button>
              ) : (
                <button
                  type="button"
                  className="vz-btn-primary"
                  disabled={toggle.isPending}
                  onClick={() => toggle.mutate(true)}
                >
                  {toggle.isPending ? "…" : "Enable"}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
