import { Link, Navigate, useLocation } from "react-router-dom";
import { CheckCircle2, Copy, ExternalLink, List, UserPlus } from "lucide-react";
import { useState } from "react";
import type { AccountCreatedState } from "./WhmCreateAccountPage";

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}

function Row({
  label,
  value,
  mono,
  copyable,
}: {
  label: string;
  value: string;
  mono?: boolean;
  copyable?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  if (!value) return null;
  return (
    <div className="grid gap-1 border-b border-cp-border/70 px-4 py-2.5 sm:grid-cols-[200px_1fr] sm:items-center dark:border-ink-800">
      <p className="text-sm font-medium text-cp-muted">{label}</p>
      <div className="flex min-w-0 items-center gap-2">
        <p className={`min-w-0 break-all text-sm text-cp-text dark:text-ink-100 ${mono ? "font-mono" : ""}`}>
          {value}
        </p>
        {copyable && (
          <button
            type="button"
            className="shrink-0 text-xs text-cp-link hover:underline"
            onClick={() => {
              void copyText(value).then(() => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1500);
              });
            }}
          >
            {copied ? "Copied" : <Copy className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>
    </div>
  );
}

export function WhmAccountCreatedPage() {
  const location = useLocation();
  const state = location.state as AccountCreatedState | null;

  if (!state?.username) {
    return <Navigate to="/whm/accounts/create" replace />;
  }

  const siteUrl = state.primary_domain || state.domain;
  const httpUrl = siteUrl ? `http://${siteUrl}` : "";

  return (
    <div className="mx-auto max-w-3xl space-y-4 animate-fade-up">
      <div className="overflow-hidden rounded-lg border border-emerald-200 bg-white shadow-panel dark:border-emerald-900 dark:bg-ink-950">
        <div className="flex items-center gap-3 border-b border-emerald-200 bg-emerald-50 px-4 py-4 dark:border-emerald-900 dark:bg-emerald-950/40">
          <CheckCircle2 className="h-8 w-8 shrink-0 text-cp-success" />
          <div>
            <h1 className="text-lg font-semibold text-cp-success">Account Creation Complete!!!</h1>
            <p className="text-sm text-cp-muted">
              The account <span className="font-mono font-medium text-cp-text">{state.username}</span>{" "}
              has been created successfully.
            </p>
          </div>
        </div>

        <div className="border-b border-cp-border bg-cp-header px-4 py-2 text-xs font-bold uppercase tracking-wide text-white dark:border-ink-800">
          Account Information
        </div>

        <Row label="Domain" value={state.primary_domain || state.domain} mono copyable />
        <Row label="Username" value={state.username} mono copyable />
        <Row label="Password" value={state.password} mono copyable />
        <Row label="Contact Email" value={state.email} copyable />
        <Row label="Package" value={state.package_name} />
        <Row label="Home Directory" value={state.home_directory} mono copyable />
        <Row label="IP Address" value={state.public_ip} mono copyable />

        {state.nameservers.length > 0 && (
          <>
            <div className="border-b border-cp-border bg-cp-header px-4 py-2 text-xs font-bold uppercase tracking-wide text-white dark:border-ink-800">
              Nameservers
            </div>
            {state.nameservers.map((ns, i) => (
              <Row key={ns} label={`Nameserver ${i + 1}`} value={ns} mono copyable />
            ))}
          </>
        )}

        <div className="space-y-2 bg-cp-canvas/50 px-4 py-4 text-sm text-cp-muted dark:bg-ink-900/30">
          <p>
            Document root :{" "}
            <code className="font-mono text-cp-text">~/public_html</code> — pointez le DNS du
            domaine vers l&apos;IP du serveur pour afficher le site.
          </p>
          {httpUrl && (
            <a
              href={httpUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 font-medium text-cp-link hover:underline"
            >
              <ExternalLink className="h-4 w-4" />
              Visit {siteUrl}
            </a>
          )}
        </div>

        <div className="flex flex-wrap gap-2 border-t border-cp-border px-4 py-3 dark:border-ink-800">
          <Link to="/whm/accounts/create" className="whm-btn-create">
            <UserPlus className="h-4 w-4" />
            Create Another Account
          </Link>
          <Link to="/whm/accounts" className="vz-btn-ghost">
            <List className="h-4 w-4" />
            List Accounts
          </Link>
          <Link to="/whm" className="vz-btn-ghost">
            Go to WHM Home
          </Link>
        </div>
      </div>
    </div>
  );
}
