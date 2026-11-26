import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

type ApiFunc = { name: string; kind: "whm" | "uapi"; summary: string; params: string[] };

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
  active: boolean;
  token?: string;
};

const AUDIENCE: Record<string, string> = {
  uapi: "Compte (UAPI)",
  whm: "WHM",
  both: "WHM + compte",
};

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
  const [days, setDays] = useState("");
  const [ips, setIps] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [allScopes, setAllScopes] = useState(true);
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      apiRequest<{ data: ApiTokenRow }>("/api-tokens/", {
        method: "POST",
        body: JSON.stringify({
          name,
          audience,
          scopes: allScopes ? ["*"] : picked,
          ip_allowlist: ips,
          expires_in_days: days ? Number(days) : null,
        }),
      }),
    onSuccess: (res) => {
      setSecret(res.data.token || null);
      setName("");
      setError(null);
      qc.invalidateQueries({ queryKey: ["api-tokens"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const revoke = useMutation({
    mutationFn: (id: number) => apiRequest(`/api-tokens/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-tokens"] }),
  });

  const funcs = (catalog.data?.data || []).filter((fn) =>
    audience === "both" ? true : fn.kind === audience,
  );
  const origin = typeof window !== "undefined" ? window.location.origin : "https://panneau.example";

  function onCreate(e: FormEvent) {
    e.preventDefault();
    setSecret(null);
    create.mutate();
  }

  function toggle(fn: string) {
    setAllScopes(false);
    setPicked((cur) => (cur.includes(fn) ? cur.filter((x) => x !== fn) : [...cur, fn]));
  }

  return (
    <div className="space-y-4 p-4">
      <div className="whm-page-head">
        <div className="whm-page-head-bar">
          <h1 className="text-sm font-semibold uppercase tracking-wide">{title}</h1>
          <p className="text-[11px] text-white/70">
            Donnez un nom, puis cliquez sur « Générer la clé API ». Le secret n’apparaît qu’une seule fois.
          </p>
        </div>
      </div>

      {secret && (
        <div className="rounded border border-amber-400/60 bg-amber-50 p-3 text-sm text-amber-950">
          <p className="font-semibold">Copiez ce jeton maintenant. Il ne sera plus affiché.</p>
          <code className="mt-2 block break-all rounded bg-white px-2 py-1 text-xs">{secret}</code>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <form onSubmit={onCreate} className="grid gap-3 rounded border border-cp-line bg-white p-4 md:grid-cols-2">
        <label className="text-xs">
          Nom
          <input className="vz-input mt-1" value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} />
        </label>
        <label className="text-xs">
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
        <label className="text-xs">
          Expiration (jours, vide = jamais)
          <input className="vz-input mt-1" value={days} onChange={(e) => setDays(e.target.value)} inputMode="numeric" />
        </label>
        <label className="text-xs">
          IP autorisées (vide = toutes)
          <input className="vz-input mt-1" value={ips} onChange={(e) => setIps(e.target.value)} placeholder="203.0.113.10, 10.0.0.0/24" />
        </label>
        <label className="flex items-center gap-2 text-xs md:col-span-2">
          <input type="checkbox" checked={allScopes} onChange={(e) => setAllScopes(e.target.checked)} />
          Toutes les fonctions de cette portée
        </label>
        {!allScopes && (
          <div className="max-h-48 overflow-auto rounded border border-cp-line p-2 text-xs md:col-span-2">
            {funcs.map((fn) => (
              <label key={fn.name} className="flex gap-2 py-0.5">
                <input type="checkbox" checked={picked.includes(fn.name)} onChange={() => toggle(fn.name)} />
                <span>
                  <code>{fn.name}</code> — {fn.summary}
                </span>
              </label>
            ))}
          </div>
        )}
        <div className="md:col-span-2">
          <button className="vz-btn-primary" type="submit" disabled={create.isPending}>
            {create.isPending ? "Génération…" : "Générer la clé API"}
          </button>
        </div>
      </form>

      <div className="overflow-auto rounded border border-cp-line bg-white">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2">Nom</th>
              <th className="px-3 py-2">Préfixe</th>
              <th className="px-3 py-2">Portée</th>
              <th className="px-3 py-2">Dernier usage</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {(tokens.data?.data || []).map((row) => (
              <tr key={row.id} className="border-t border-cp-line">
                <td className="px-3 py-2">
                  {row.name}
                  {!row.active && <span className="ml-2 text-red-600">révoqué</span>}
                </td>
                <td className="px-3 py-2 font-mono">{row.prefix}…</td>
                <td className="px-3 py-2">{AUDIENCE[row.audience] || row.audience}</td>
                <td className="px-3 py-2">
                  {row.last_used_at ? new Date(row.last_used_at).toLocaleString("fr-FR") : "—"}
                  {row.last_used_ip ? ` · ${row.last_used_ip}` : ""}
                </td>
                <td className="px-3 py-2 text-right">
                  {row.active && (
                    <button type="button" className="text-red-700 underline" onClick={() => revoke.mutate(row.id)}>
                      Révoquer
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!tokens.isLoading && (tokens.data?.data || []).length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Aucun jeton.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <section className="space-y-2 rounded border border-cp-line bg-white p-4 text-sm">
        <h2 className="text-sm font-semibold">Appel</h2>
        <p>
          WHM : <code>GET {origin}/api/json-api/listaccts</code>
        </p>
        <p>
          Compte : <code>GET {origin}/api/execute/DomainInfo/list_domains</code>
        </p>
        <pre className="overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">{`curl -H "Authorization: whm UTILISATEUR:JETON" \\
  -H "Content-Type: application/json" \\
  -d '{"method":"GET","path":"/api/v1/packages/"}' \\
  ${origin}/api/json-api/apirequest

curl -H "Authorization: cpanel UTILISATEUR:JETON" \\
  ${origin}/api/execute/Email/list_pops`}</pre>
        <p className="text-xs text-cp-muted">
          Documentation complète : <code>docs/cpanel-api.md</code>. Le paramètre <code>account</code> permet à un
          admin ou revendeur d’agir sur un compte enfant en UAPI.
        </p>
        <details>
          <summary className="cursor-pointer text-xs font-semibold">Fonctions disponibles</summary>
          <ul className="mt-2 max-h-64 space-y-1 overflow-auto text-xs">
            {(catalog.data?.data || []).map((fn) => (
              <li key={fn.name}>
                <code>{fn.kind === "whm" ? `/api/json-api/${fn.name}` : `/api/execute/${fn.name.replace(".", "/")}`}</code>
                {" — "}
                {fn.summary}
                {fn.params.length > 0 && <span className="text-cp-muted"> ({fn.params.join(", ")})</span>}
              </li>
            ))}
          </ul>
        </details>
      </section>
    </div>
  );
}
