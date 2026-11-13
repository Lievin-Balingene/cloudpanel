import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, RefreshCw, X } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { formatBytes } from "@/lib/format";

type LogMeta = {
  kind: string;
  engine: string;
  label: string;
  domain: string;
  path: string;
  exists: boolean;
  size_bytes: number;
  modified_at: string | null;
};

type DomainLogs = {
  id: number;
  name: string;
  domain_type: string;
  logs: LogMeta[];
  available_count: number;
};

type LogsIndex = {
  username: string;
  user_id: number;
  domains: DomainLogs[];
  total_available: number;
  focus_domain?: string;
};

type TailPayload = {
  domain: string;
  kind: string;
  path: string;
  exists: boolean;
  lines: string[];
  line_count: number;
  size_bytes: number;
  truncated: boolean;
  modified_at?: string;
};

export function AccountLogsModal({
  userId,
  username,
  domainId,
  initialDomain,
  onClose,
}: {
  userId?: number;
  username: string;
  /** Mode domaine (client/WHM Domains) — n'exige pas CanManageUsers. */
  domainId?: number;
  initialDomain?: string;
  onClose: () => void;
}) {
  const [domain, setDomain] = useState(initialDomain || "");
  const [kind, setKind] = useState("access");
  const [lines, setLines] = useState(200);

  const indexPath = domainId
    ? `/domains/${domainId}/logs/`
    : `/auth/users/${userId}/logs/`;

  const indexQuery = useQuery({
    queryKey: ["account-logs", userId ?? null, domainId ?? null],
    queryFn: () => apiRequest<LogsIndex>(indexPath),
    enabled: Boolean(domainId || userId),
  });

  const domains = indexQuery.data?.domains ?? [];

  useEffect(() => {
    if (!domains.length) return;
    const focus = initialDomain || indexQuery.data?.focus_domain;
    if (focus && domains.some((d) => d.name === focus) && domain !== focus) {
      setDomain(focus);
      return;
    }
    if (!domain || !domains.some((d) => d.name === domain)) {
      const preferred =
        (focus && domains.find((d) => d.name === focus)) ||
        domains.find((d) => d.available_count > 0) ||
        domains[0];
      setDomain(preferred.name);
      const firstLog = preferred.logs.find((l) => l.exists) || preferred.logs[0];
      if (firstLog) setKind(firstLog.kind);
    }
  }, [domains, domain, initialDomain, indexQuery.data?.focus_domain]);

  const currentDomain = useMemo(
    () => domains.find((d) => d.name === domain) || null,
    [domains, domain],
  );

  const availableKinds = currentDomain?.logs.filter((l) => l.exists) ?? [];
  const allKinds = currentDomain?.logs ?? [];

  useEffect(() => {
    if (!currentDomain) return;
    const stillOk = currentDomain.logs.some((l) => l.kind === kind && l.exists);
    if (!stillOk) {
      const next = currentDomain.logs.find((l) => l.exists);
      if (next) setKind(next.kind);
    }
  }, [currentDomain, kind]);

  const selectedDomainId = currentDomain?.id ?? domainId;

  const tailPath = domainId
    ? `/domains/${domainId}/logs/tail/?kind=${encodeURIComponent(kind)}&lines=${lines}`
    : selectedDomainId && !userId
      ? `/domains/${selectedDomainId}/logs/tail/?kind=${encodeURIComponent(kind)}&lines=${lines}`
      : `/auth/users/${userId}/logs/tail/?domain=${encodeURIComponent(domain)}&kind=${encodeURIComponent(kind)}&lines=${lines}`;

  const tailQuery = useQuery({
    queryKey: ["account-logs-tail", userId ?? null, domainId ?? selectedDomainId, domain, kind, lines],
    queryFn: () => apiRequest<TailPayload>(tailPath),
    enabled: Boolean((domainId || userId) && (domain || domainId) && kind),
    refetchInterval: false,
  });

  const meta = allKinds.find((l) => l.kind === kind);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/45 p-0 sm:items-center sm:p-4">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Fermer" onClick={onClose} />
      <div
        className="relative z-10 flex h-[min(92dvh,820px)] w-full max-w-5xl flex-col overflow-hidden rounded-t-[14px] border border-cp-border bg-white shadow-xl dark:border-ink-700 dark:bg-ink-950 sm:rounded-[10px]"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-cp-border px-4 py-3 dark:border-ink-800">
          <div className="min-w-0">
            <p className="flex items-center gap-2 font-semibold text-cp-text">
              <FileText className="h-4 w-4 text-cp-orange" />
              Logs · <span className="font-mono">{username}</span>
            </p>
            <p className="mt-0.5 text-xs text-cp-muted">
              Journaux web par domaine (nginx / OpenLiteSpeed) — Raw Access / Error Log
            </p>
          </div>
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-cp-muted hover:bg-cp-canvas"
            onClick={onClose}
            aria-label="Fermer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex shrink-0 flex-wrap items-end gap-2 border-b border-cp-border px-4 py-2.5 dark:border-ink-800">
          <label className="min-w-[10rem] flex-1 space-y-1 text-xs">
            <span className="text-cp-muted">Domaine</span>
            <select
              className="vz-input !py-1.5 text-sm"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              disabled={indexQuery.isLoading || !domains.length || Boolean(domainId)}
            >
              {!domains.length && <option value="">Aucun domaine</option>}
              {domains.map((d) => (
                <option key={d.id} value={d.name}>
                  {d.name}
                  {d.available_count ? ` (${d.available_count} log)` : " — aucun fichier"}
                </option>
              ))}
            </select>
          </label>
          <label className="min-w-[9rem] space-y-1 text-xs">
            <span className="text-cp-muted">Journal</span>
            <select
              className="vz-input !py-1.5 text-sm"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              {(availableKinds.length ? availableKinds : allKinds).map((l) => (
                <option key={l.kind} value={l.kind} disabled={!l.exists}>
                  {l.label}
                  {!l.exists ? " (absent)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-cp-muted">Lignes</span>
            <select
              className="vz-input !w-auto !py-1.5 text-sm"
              value={lines}
              onChange={(e) => setLines(Number(e.target.value))}
            >
              <option value={100}>100</option>
              <option value={200}>200</option>
              <option value={500}>500</option>
              <option value={1000}>1000</option>
            </select>
          </label>
          <button
            type="button"
            className="vz-btn-ghost vz-btn-sm"
            disabled={tailQuery.isFetching}
            onClick={() => void tailQuery.refetch()}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${tailQuery.isFetching ? "animate-spin" : ""}`} />
            Actualiser
          </button>
        </div>

        <div className="flex shrink-0 flex-wrap gap-x-4 gap-y-1 border-b border-cp-border bg-cp-canvas/60 px-4 py-1.5 text-[10px] text-cp-muted dark:border-ink-800 dark:bg-ink-900/40">
          {meta && (
            <>
              <span>
                Fichier : <span className="font-mono text-cp-text">{meta.path}</span>
              </span>
              <span>Taille : {meta.exists ? formatBytes(meta.size_bytes) : "—"}</span>
              {tailQuery.data?.truncated ? (
                <span className="text-amber-700">Tronqué (fin du fichier)</span>
              ) : null}
            </>
          )}
          {indexQuery.data && (
            <span className="ml-auto">
              {indexQuery.data.total_available} journal(aux) · {domains.length} domaine(s)
            </span>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-auto bg-[#0f172a] p-3 font-mono text-[11px] leading-relaxed text-slate-100">
          {indexQuery.isLoading && <p className="text-slate-400">Chargement de l&apos;index…</p>}
          {indexQuery.isError && (
            <p className="text-red-300">
              {indexQuery.error instanceof Error ? indexQuery.error.message : "Index impossible."}
            </p>
          )}
          {!indexQuery.isLoading && !domains.length && (
            <p className="text-slate-400">Aucun domaine lié à ce compte.</p>
          )}
          {tailQuery.isLoading && <p className="text-slate-400">Lecture du journal…</p>}
          {tailQuery.isError && (
            <p className="text-red-300">
              {tailQuery.error instanceof Error ? tailQuery.error.message : "Lecture impossible."}
            </p>
          )}
          {tailQuery.data && !tailQuery.data.exists && (
            <p className="text-slate-400">
              Fichier absent — pas encore de trafic, ou logs non générés pour ce domaine.
            </p>
          )}
          {tailQuery.data?.exists && tailQuery.data.lines.length === 0 && (
            <p className="text-slate-400">Journal vide.</p>
          )}
          {tailQuery.data?.lines.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all border-b border-white/5 py-0.5">
              <span className="mr-2 select-none text-slate-500">{i + 1}</span>
              {line}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
