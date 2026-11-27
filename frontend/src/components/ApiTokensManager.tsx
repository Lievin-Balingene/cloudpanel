import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

type ApiFunc = { name: string; kind: "whm" | "uapi"; summary: string; params: string[] };

type TokenStatus = "active" | "suspended" | "expired" | "revoked";

type ApiTokenRow = {
  id: number;
  name: string;
  prefix: string;
  audience: "uapi" | "whm" | "both";
  scopes: string[];
  ip_allowlist: string;
  expires_at: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
  created_at: string | null;
  revoked: boolean;
  suspended: boolean;
  status: TokenStatus;
  active: boolean;
  token?: string;
};

const AUDIENCE: Record<string, string> = {
  uapi: "Compte (UAPI)",
  whm: "WHM",
  both: "WHM + compte",
};

const STATUS: Record<TokenStatus, { label: string; className: string }> = {
  active: { label: "Active", className: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  suspended: { label: "Suspendue", className: "bg-amber-50 text-amber-900 ring-amber-200" },
  expired: { label: "Expirée", className: "bg-slate-100 text-slate-600 ring-slate-200" },
  revoked: { label: "Révoquée", className: "bg-red-50 text-red-800 ring-red-200" },
};

const PRESETS = [
  { id: "never", label: "Jamais" },
  { id: "30", label: "30 jours" },
  { id: "90", label: "90 jours" },
  { id: "365", label: "1 an" },
  { id: "date", label: "Date précise" },
] as const;

function formatWhen(value: string | null) {
  if (!value) return "Jamais";
  return new Date(value).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function todayIso() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

export function ApiTokensManager({
  title,
  allowWhm,
}: {
  title: string;
  allowWhm: boolean;
}) {
  const qc = useQueryClient();
  const tokens = useQuery({
    queryKey: ["api-tokens"],
    queryFn: () => apiRequest<{ data: ApiTokenRow[] }>("/api-tokens/"),
  });
  const catalog = useQuery({
    queryKey: ["api-token-catalog"],
    queryFn: () => apiRequest<{ data: ApiFunc[] }>("/api-tokens/catalog/"),
  });
  const [name, setName] = useState("");
  const [audience, setAudience] = useState<"uapi" | "whm" | "both">(allowWhm ? "both" : "uapi");
  const [preset, setPreset] = useState<(typeof PRESETS)[number]["id"]>("never");
  const [date, setDate] = useState("");
  const [ips, setIps] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [allScopes, setAllScopes] = useState(true);
  const [scopeQuery, setScopeQuery] = useState("");
  const [secret, setSecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [editDate, setEditDate] = useState("");
  const [confirmRevoke, setConfirmRevoke] = useState<number | null>(null);

  const create = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        name,
        audience,
        scopes: allScopes ? ["*"] : picked,
        ip_allowlist: ips,
      };
      if (preset === "date") body.expires_at = date;
      else if (preset !== "never") body.expires_in_days = Number(preset);
      return apiRequest<{ data: ApiTokenRow }>("/api-tokens/", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    onSuccess: (res) => {
      setSecret(res.data.token || null);
      setCopied(false);
      setName("");
      setError(null);
      qc.invalidateQueries({ queryKey: ["api-tokens"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const patch = useMutation({
    mutationFn: (payload: { id: number; body: Record<string, unknown> }) =>
      apiRequest(`/api-tokens/${payload.id}/`, {
        method: "PATCH",
        body: JSON.stringify(payload.body),
      }),
    onSuccess: () => {
      setEditing(null);
      setError(null);
      qc.invalidateQueries({ queryKey: ["api-tokens"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const revoke = useMutation({
    mutationFn: (id: number) => apiRequest(`/api-tokens/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      setConfirmRevoke(null);
      qc.invalidateQueries({ queryKey: ["api-tokens"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const funcs = useMemo(() => {
    const q = scopeQuery.trim().toLowerCase();
    return (catalog.data?.data || []).filter((fn) => {
      if (audience !== "both" && fn.kind !== audience) return false;
      if (!q) return true;
      return `${fn.name} ${fn.summary}`.toLowerCase().includes(q);
    });
  }, [catalog.data, audience, scopeQuery]);

  const rows = tokens.data?.data || [];
  const origin = typeof window !== "undefined" ? window.location.origin : "https://panneau.example";

  function onCreate(e: FormEvent) {
    e.preventDefault();
    if (preset === "date" && !date) {
      setError("Choisissez une date d’expiration.");
      return;
    }
    if (!allScopes && picked.length === 0) {
      setError("Choisissez au moins une fonction, ou cochez « Toutes les fonctions ».");
      return;
    }
    setSecret(null);
    create.mutate();
  }

  async function copySecret() {
    if (!secret) return;
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="space-y-4 p-4">
      <div className="whm-page-head">
        <div className="whm-page-head-bar">
          <h1 className="text-sm font-semibold uppercase tracking-wide">{title}</h1>
          <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-white/80">
            Une clé appelle le panneau à votre place. Le secret ne s’affiche qu’une fois. Vous pouvez la suspendre,
            la réactiver, ou fixer la date où elle cesse de fonctionner. La révocation est définitive.
          </p>
        </div>
      </div>

      {secret && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
          <p className="font-semibold">Copiez cette clé maintenant. Elle ne sera plus affichée.</p>
          <code className="mt-2 block break-all rounded-md bg-white px-3 py-2 font-mono text-xs">{secret}</code>
          <button type="button" className="vz-btn-ghost mt-3" onClick={() => void copySecret()}>
            {copied ? "Copiée" : "Copier la clé"}
          </button>
        </div>
      )}
      {error && <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="grid items-start gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <form onSubmit={onCreate} className="space-y-3 rounded-lg border border-cp-line bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-cp-text">Nouvelle clé</h2>
          <label className="block text-xs font-medium text-cp-text">
            Nom
            <input
              className="vz-input mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={80}
              placeholder="Production, script facturation…"
            />
          </label>
          <label className="block text-xs font-medium text-cp-text">
            Portée
            <select
              className="vz-input mt-1"
              value={audience}
              onChange={(e) => setAudience(e.target.value as "uapi" | "whm" | "both")}
            >
              <option value="uapi">Compte (UAPI)</option>
              {allowWhm && <option value="whm">WHM</option>}
              {allowWhm && <option value="both">WHM + compte</option>}
            </select>
          </label>
          <fieldset className="space-y-2">
            <legend className="text-xs font-medium text-cp-text">Expiration</legend>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`rounded-full px-2.5 py-1 text-[11px] ring-1 ${
                    preset === item.id
                      ? "bg-[#2a4a6b] text-white ring-[#2a4a6b]"
                      : "bg-white text-cp-text ring-cp-line hover:bg-slate-50"
                  }`}
                  onClick={() => setPreset(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            {preset === "date" && (
              <input
                className="vz-input"
                type="date"
                min={todayIso()}
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            )}
            <p className="text-[11px] text-cp-muted">
              Une date précise reste valable jusqu’à la fin de cette journée (UTC).
            </p>
          </fieldset>
          <label className="block text-xs font-medium text-cp-text">
            IP autorisées
            <input
              className="vz-input mt-1"
              value={ips}
              onChange={(e) => setIps(e.target.value)}
              placeholder="Vide = toutes. Ex. 203.0.113.10, 10.0.0.0/24"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-cp-text">
            <input type="checkbox" checked={allScopes} onChange={(e) => setAllScopes(e.target.checked)} />
            Toutes les fonctions de cette portée
          </label>
          {!allScopes && (
            <div className="space-y-2">
              <input
                className="vz-input"
                value={scopeQuery}
                onChange={(e) => setScopeQuery(e.target.value)}
                placeholder="Filtrer les fonctions"
              />
              <div className="max-h-48 overflow-auto rounded border border-cp-line p-2 text-xs">
                {funcs.map((fn) => (
                  <label key={fn.name} className="flex gap-2 py-1">
                    <input
                      type="checkbox"
                      checked={picked.includes(fn.name)}
                      onChange={() =>
                        setPicked((cur) => (cur.includes(fn.name) ? cur.filter((x) => x !== fn.name) : [...cur, fn.name]))
                      }
                    />
                    <span>
                      <code>{fn.name}</code>
                      <span className="text-cp-muted"> — {fn.summary}</span>
                    </span>
                  </label>
                ))}
                {funcs.length === 0 && <p className="text-cp-muted">Aucune fonction.</p>}
              </div>
            </div>
          )}
          <button className="vz-btn-primary w-full" type="submit" disabled={create.isPending}>
            {create.isPending ? "Génération…" : "Générer la clé API"}
          </button>
        </form>

        <div className="space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-cp-text">Clés</h2>
            <p className="text-[11px] text-cp-muted">{rows.length} / 25</p>
          </div>
          {tokens.isLoading && <p className="text-sm text-cp-muted">Chargement…</p>}
          {!tokens.isLoading && rows.length === 0 && (
            <div className="rounded-lg border border-dashed border-cp-line bg-white px-4 py-8 text-center text-sm text-cp-muted">
              Aucune clé pour l’instant. Le formulaire à gauche en crée une.
            </div>
          )}
          {rows.map((row) => {
            const badge = STATUS[row.status] || STATUS.revoked;
            const locked = row.status === "revoked";
            return (
              <article key={row.id} className="rounded-lg border border-cp-line bg-white p-4 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-cp-text">{row.name}</h3>
                    <p className="mt-0.5 font-mono text-[11px] text-cp-muted">{row.prefix}…</p>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${badge.className}`}>
                    {badge.label}
                  </span>
                </div>
                <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                  <div>
                    <dt className="text-cp-muted">Portée</dt>
                    <dd>{AUDIENCE[row.audience] || row.audience}</dd>
                  </div>
                  <div>
                    <dt className="text-cp-muted">Expire</dt>
                    <dd>{formatWhen(row.expires_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-cp-muted">Dernier usage</dt>
                    <dd>
                      {row.last_used_at ? formatWhen(row.last_used_at) : "Jamais"}
                      {row.last_used_ip ? ` · ${row.last_used_ip}` : ""}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-cp-muted">Fonctions</dt>
                    <dd>{row.scopes.includes("*") ? "Toutes" : row.scopes.join(", ") || "—"}</dd>
                  </div>
                </dl>
                {!locked && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {row.status === "suspended" && (
                      <button
                        type="button"
                        className="vz-btn-sm vz-btn-primary"
                        disabled={patch.isPending}
                        onClick={() => patch.mutate({ id: row.id, body: { suspended: false } })}
                      >
                        Réactiver
                      </button>
                    )}
                    {row.status === "active" && (
                      <button
                        type="button"
                        className="vz-btn-sm vz-btn-ghost"
                        disabled={patch.isPending}
                        onClick={() => patch.mutate({ id: row.id, body: { suspended: true } })}
                      >
                        Suspendre
                      </button>
                    )}
                    <button
                      type="button"
                      className="vz-btn-sm vz-btn-ghost"
                      onClick={() => {
                        setEditing(editing === row.id ? null : row.id);
                        setEditDate(row.expires_at ? row.expires_at.slice(0, 10) : "");
                      }}
                    >
                      Expiration
                    </button>
                    {confirmRevoke === row.id ? (
                      <>
                        <button
                          type="button"
                          className="vz-btn-sm bg-red-700 text-white"
                          disabled={revoke.isPending}
                          onClick={() => revoke.mutate(row.id)}
                        >
                          Confirmer la révocation
                        </button>
                        <button type="button" className="vz-btn-sm vz-btn-ghost" onClick={() => setConfirmRevoke(null)}>
                          Annuler
                        </button>
                      </>
                    ) : (
                      <button type="button" className="vz-btn-sm border border-red-200 text-red-700" onClick={() => setConfirmRevoke(row.id)}>
                        Révoquer
                      </button>
                    )}
                  </div>
                )}
                {editing === row.id && !locked && (
                  <div className="mt-3 flex flex-wrap items-end gap-2 rounded-md bg-slate-50 p-3">
                    <label className="text-[11px] text-cp-muted">
                      Valable jusqu’au
                      <input
                        className="vz-input mt-1"
                        type="date"
                        min={todayIso()}
                        value={editDate}
                        onChange={(e) => setEditDate(e.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      className="vz-btn-sm vz-btn-primary"
                      disabled={!editDate || patch.isPending}
                      onClick={() => patch.mutate({ id: row.id, body: { expires_at: editDate } })}
                    >
                      Enregistrer
                    </button>
                    <button
                      type="button"
                      className="vz-btn-sm vz-btn-ghost"
                      disabled={patch.isPending}
                      onClick={() => patch.mutate({ id: row.id, body: { expires_at: null } })}
                    >
                      Sans expiration
                    </button>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      </div>

      <details className="rounded-lg border border-cp-line bg-white p-4 text-sm">
        <summary className="cursor-pointer text-sm font-semibold">Comment appeler l’API</summary>
        <pre className="mt-3 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">{`curl -H "Authorization: whm UTILISATEUR:CLE" \\
  ${origin}/api/json-api/listaccts

curl -H "Authorization: cpanel UTILISATEUR:CLE" \\
  ${origin}/api/execute/Email/list_pops`}</pre>
        <p className="mt-2 text-xs text-cp-muted">
          {funcs.length > 0 ? `${catalog.data?.data.length || 0} fonctions.` : "Le catalogue se charge avec la page."} Une
          clé suspendue ou expirée répond 401.
        </p>
      </details>
    </div>
  );
}
