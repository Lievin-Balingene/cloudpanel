import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Ban,
  Check,
  Network,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { EmptyState, PageHeader, Tabs } from "@/components/ui/PageChrome";

interface DomainIpRow {
  id: number;
  name: string;
  domain_type: string;
  owner: string;
  owner_id: number;
  ipv4_address: string | null;
}

interface IpUsageRow {
  ip: string;
  is_primary: boolean;
  domain_count: number;
  account_count: number;
  accounts: string[];
  domains: DomainIpRow[];
}

interface DenyRule {
  id: number;
  name: string;
  source_cidr: string;
  protocol: string;
  port_start: number | null;
  port_end: number | null;
  is_applied: boolean;
  notes: string;
}

interface IpFunctionsData {
  public_ip: string;
  server_ips: string[];
  extra_ips: string[];
  usage: IpUsageRow[];
  deny_rules: DenyRule[];
  totals: { ips: number; domains: number; deny_rules: number };
}

export function IpFunctionsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState("usage");
  const [extraIp, setExtraIp] = useState("");
  const [denyIp, setDenyIp] = useState("");
  const [changeDomainId, setChangeDomainId] = useState("");
  const [changeIp, setChangeIp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["ip-functions"],
    queryFn: () => apiRequest<IpFunctionsData>("/server-setup/ip-functions/"),
  });

  const allDomains = useMemo(() => {
    const rows: DomainIpRow[] = [];
    for (const u of data?.usage || []) {
      rows.push(...u.domains);
    }
    return rows.sort((a, b) => a.name.localeCompare(b.name));
  }, [data]);

  useEffect(() => {
    if (!changeDomainId && allDomains[0]) {
      setChangeDomainId(String(allDomains[0].id));
      setChangeIp(allDomains[0].ipv4_address || data?.public_ip || "");
    }
  }, [allDomains, changeDomainId, data?.public_ip]);

  const addExtra = useMutation({
    mutationFn: (ip: string) =>
      apiRequest<IpFunctionsData>("/server-setup/ip-functions/extra/", {
        method: "POST",
        body: JSON.stringify({ ip }),
      }),
    onSuccess: () => {
      setExtraIp("");
      setOkMsg("IP ajoutée.");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["ip-functions"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const removeExtra = useMutation({
    mutationFn: (ip: string) =>
      apiRequest<IpFunctionsData>("/server-setup/ip-functions/extra/", {
        method: "DELETE",
        body: JSON.stringify({ ip }),
      }),
    onSuccess: () => {
      setOkMsg("IP retirée.");
      void qc.invalidateQueries({ queryKey: ["ip-functions"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const changeSite = useMutation({
    mutationFn: () =>
      apiRequest("/server-setup/ip-functions/change-site/", {
        method: "POST",
        body: JSON.stringify({
          domain_id: Number(changeDomainId),
          ipv4_address: changeIp || null,
        }),
      }),
    onSuccess: () => {
      setOkMsg("IP du site mise à jour (vhost + DNS A si possible).");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["ip-functions"] });
      void qc.invalidateQueries({ queryKey: ["domains"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const denyMut = useMutation({
    mutationFn: (ip: string) =>
      apiRequest("/firewall/rules/", {
        method: "POST",
        body: JSON.stringify({
          name: `deny-${ip.replace(/[^\w.-]/g, "_")}`,
          action: "deny",
          protocol: "any",
          direction: "in",
          source_cidr: ip.includes("/") ? ip : `${ip}/32`,
          apply_now: true,
          notes: "IP Deny Manager",
        }),
      }),
    onSuccess: () => {
      setDenyIp("");
      setOkMsg("IP bloquée.");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["ip-functions"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const undenyMut = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/firewall/rules/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      setOkMsg("Blocage retiré.");
      void qc.invalidateQueries({ queryKey: ["ip-functions"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  function onAddExtra(e: FormEvent) {
    e.preventDefault();
    if (!extraIp.trim()) return;
    addExtra.mutate(extraIp.trim());
  }

  function onDeny(e: FormEvent) {
    e.preventDefault();
    if (!denyIp.trim()) return;
    denyMut.mutate(denyIp.trim());
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={title}
        subtitle="Show IP Address Usage · Change Site IP · IP Deny Manager"
        stats={[
          { label: "IP publique", value: data?.public_ip || "—" },
          { label: "IP suivies", value: data?.totals.ips ?? "—" },
          { label: "Domaines", value: data?.totals.domains ?? "—" },
          { label: "Deny", value: data?.totals.deny_rules ?? "—" },
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

      {(error || okMsg) && (
        <div
          className={`rounded-lg border px-3 py-2 text-sm ${
            error
              ? "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200"
              : "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-950/30"
          }`}
        >
          {error || okMsg}
        </div>
      )}

      <Tabs
        tabs={[
          { id: "usage", label: "IP Address Usage" },
          { id: "change", label: "Change Site IP" },
          { id: "deny", label: "IP Deny Manager" },
          { id: "extra", label: "Add IP Address" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {isLoading ? (
        <p className="text-sm text-cp-muted">Chargement…</p>
      ) : tab === "usage" ? (
        <div className="space-y-3">
          {(data?.usage || []).length === 0 ? (
            <EmptyState icon={<Network className="h-8 w-8" />} message="Aucune utilisation IP." />
          ) : (
            (data?.usage || []).map((row) => (
              <div key={row.ip} className="vz-panel overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cp-border/70 px-3.5 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-semibold">{row.ip}</span>
                    {row.is_primary && (
                      <span className="rounded-full bg-cp-navy/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-cp-navy dark:bg-white/10 dark:text-white/80">
                        Primary
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-cp-muted">
                    {row.domain_count} domaine(s) · {row.account_count} compte(s)
                  </p>
                </div>
                {row.domains.length === 0 ? (
                  <p className="px-3.5 py-3 text-xs text-cp-muted">Aucun domaine sur cette IP.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="text-[11px] uppercase tracking-wide text-cp-muted">
                        <tr>
                          <th className="px-3.5 py-2 font-semibold">Domaine</th>
                          <th className="px-3.5 py-2 font-semibold">Compte</th>
                          <th className="px-3.5 py-2 font-semibold">Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {row.domains.map((d) => (
                          <tr key={d.id} className="border-t border-cp-border/50">
                            <td className="px-3.5 py-2 font-medium">{d.name}</td>
                            <td className="px-3.5 py-2 text-cp-muted">{d.owner || "—"}</td>
                            <td className="px-3.5 py-2 text-cp-muted">{d.domain_type}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      ) : tab === "change" ? (
        <form
          className="vz-panel space-y-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            changeSite.mutate();
          }}
        >
          <p className="text-sm text-cp-muted">
            Assigne une IPv4 au domaine (met à jour le vhost et l’enregistrement A si une zone DNS est liée).
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-cp-muted">Compte / domaine</span>
              <select
                className="mt-1 vz-input"
                value={changeDomainId}
                onChange={(e) => {
                  setChangeDomainId(e.target.value);
                  const d = allDomains.find((x) => String(x.id) === e.target.value);
                  setChangeIp(d?.ipv4_address || data?.public_ip || "");
                }}
              >
                {allDomains.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.owner || "?"})
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-cp-muted">Nouvelle IP</span>
              <select
                className="mt-1 vz-input"
                value={changeIp}
                onChange={(e) => setChangeIp(e.target.value)}
              >
                {(data?.server_ips || []).map((ip) => (
                  <option key={ip} value={ip}>
                    {ip}
                    {ip === data?.public_ip ? " (primary)" : ""}
                  </option>
                ))}
              </select>
              <input
                className="mt-2 vz-input font-mono text-sm"
                value={changeIp}
                onChange={(e) => setChangeIp(e.target.value)}
                placeholder="Ou saisie libre IPv4"
              />
            </label>
          </div>
          <button
            type="submit"
            className="vz-btn-primary inline-flex items-center gap-1.5"
            disabled={changeSite.isPending || !changeDomainId}
          >
            <Check className="h-4 w-4" />
            {changeSite.isPending ? "Application…" : "Change Site IP"}
          </button>
        </form>
      ) : tab === "deny" ? (
        <div className="space-y-3">
          <form className="vz-panel flex flex-wrap items-end gap-2 p-4" onSubmit={onDeny}>
            <label className="min-w-[14rem] flex-1 text-sm">
              <span className="text-cp-muted">Bloquer IP / CIDR</span>
              <input
                className="mt-1 vz-input font-mono"
                value={denyIp}
                onChange={(e) => setDenyIp(e.target.value)}
                placeholder="203.0.113.50 ou 203.0.113.0/24"
              />
            </label>
            <button type="submit" className="vz-btn-primary inline-flex items-center gap-1.5" disabled={denyMut.isPending}>
              <Ban className="h-4 w-4" />
              Block IP
            </button>
          </form>
          {(data?.deny_rules || []).length === 0 ? (
            <EmptyState icon={<Ban className="h-8 w-8" />} message="Aucune IP bloquée." />
          ) : (
            <div className="vz-panel overflow-hidden">
              <table className="w-full text-left text-sm">
                <thead className="text-[11px] uppercase tracking-wide text-cp-muted">
                  <tr>
                    <th className="px-3.5 py-2">Source</th>
                    <th className="px-3.5 py-2">Règle</th>
                    <th className="px-3.5 py-2">État</th>
                    <th className="px-3.5 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {(data?.deny_rules || []).map((r) => (
                    <tr key={r.id} className="border-t border-cp-border/50">
                      <td className="px-3.5 py-2 font-mono text-xs">{r.source_cidr || "—"}</td>
                      <td className="px-3.5 py-2">{r.name}</td>
                      <td className="px-3.5 py-2 text-xs text-cp-muted">
                        {r.is_applied ? "Appliquée" : "En attente"}
                      </td>
                      <td className="px-3.5 py-2 text-right">
                        <IconAction
                          label="Retirer"
                          danger
                          onClick={() => undenyMut.mutate(r.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </IconAction>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <form className="vz-panel flex flex-wrap items-end gap-2 p-4" onSubmit={onAddExtra}>
            <label className="min-w-[14rem] flex-1 text-sm">
              <span className="text-cp-muted">Nouvelle IP serveur</span>
              <input
                className="mt-1 vz-input font-mono"
                value={extraIp}
                onChange={(e) => setExtraIp(e.target.value)}
                placeholder="198.51.100.10"
              />
            </label>
            <button type="submit" className="vz-btn-primary inline-flex items-center gap-1.5" disabled={addExtra.isPending}>
              <Plus className="h-4 w-4" />
              Add IP
            </button>
          </form>
          {(data?.extra_ips || []).length === 0 ? (
            <p className="text-sm text-cp-muted">
              Seule l’IP publique principale est enregistrée
              {data?.public_ip ? ` (${data.public_ip})` : ""}.
            </p>
          ) : (
            <ul className="vz-panel divide-y divide-cp-border/60">
              {(data?.extra_ips || []).map((ip) => (
                <li key={ip} className="flex items-center justify-between gap-2 px-3.5 py-2.5 text-sm">
                  <span className="font-mono">{ip}</span>
                  <IconAction
                    label="Supprimer"
                    danger
                    onClick={() => removeExtra.mutate(ip)}
                  >
                    <X className="h-3.5 w-3.5" />
                  </IconAction>
                </li>
              ))}
            </ul>
          )}
          <p className="flex items-start gap-2 text-xs text-cp-muted">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
            L’ajout d’IP dans V-zone enregistre l’adresse pour l’assignation de sites ; le bind OS reste à gérer côté réseau.
          </p>
        </div>
      )}
    </div>
  );
}
