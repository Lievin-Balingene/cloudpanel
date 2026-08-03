import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

interface FirewallOverview {
  rules: number;
  rules_enabled: number;
  rules_applied: number;
  jails: number;
  jails_enabled: number;
  bans_active: number;
  provision_mode: string;
}

interface FirewallRuleItem {
  id: number;
  name: string;
  action: string;
  protocol: string;
  direction: string;
  port_start: number | null;
  port_end: number | null;
  source_cidr: string;
  is_enabled: boolean;
  is_applied: boolean;
  last_error: string;
}

interface JailItem {
  id: number;
  name: string;
  is_enabled: boolean;
  currently_banned: number;
  total_banned: number;
  max_retry: number;
  ban_time: number;
}

interface BanItem {
  id: number;
  jail_name: string;
  ip_address: string;
  status: string;
  reason: string;
  banned_at: string;
}

export function FirewallManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["firewall-overview"],
    queryFn: () => apiRequest<FirewallOverview>("/firewall/overview/"),
  });
  const { data: rules = [], isLoading: loadingRules } = useQuery({
    queryKey: ["firewall-rules"],
    queryFn: () => apiRequest<FirewallRuleItem[]>("/firewall/rules/"),
  });
  const { data: jails = [] } = useQuery({
    queryKey: ["firewall-jails"],
    queryFn: () => apiRequest<JailItem[]>("/firewall/fail2ban/jails/"),
  });
  const { data: bans = [] } = useQuery({
    queryKey: ["firewall-bans"],
    queryFn: () => apiRequest<BanItem[]>("/firewall/fail2ban/bans/"),
  });

  const [ruleForm, setRuleForm] = useState({
    name: "",
    action: "allow",
    protocol: "tcp",
    port_start: 443,
    source_cidr: "",
    apply_now: true,
  });
  const [banForm, setBanForm] = useState({
    ip_address: "",
    jail_name: "sshd",
    reason: "",
  });
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["firewall-overview"] });
    void qc.invalidateQueries({ queryKey: ["firewall-rules"] });
    void qc.invalidateQueries({ queryKey: ["firewall-jails"] });
    void qc.invalidateQueries({ queryKey: ["firewall-bans"] });
  };

  const createRule = useMutation({
    mutationFn: () =>
      apiRequest("/firewall/rules/", {
        method: "POST",
        body: JSON.stringify({
          ...ruleForm,
          port_start: ruleForm.port_start || null,
        }),
      }),
    onSuccess: () => {
      setRuleForm({ name: "", action: "allow", protocol: "tcp", port_start: 443, source_cidr: "", apply_now: true });
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const applyRule = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/firewall/rules/${id}/apply/`, { method: "POST", body: "{}" }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const removeRule = useMutation({
    mutationFn: (id: number) => apiRequest(`/firewall/rules/${id}/`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const banIp = useMutation({
    mutationFn: () =>
      apiRequest("/firewall/fail2ban/ban/", {
        method: "POST",
        body: JSON.stringify(banForm),
      }),
    onSuccess: () => {
      setBanForm({ ip_address: "", jail_name: "sshd", reason: "" });
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const unbanIp = useMutation({
    mutationFn: ({ ip, jail }: { ip: string; jail: string }) =>
      apiRequest("/firewall/fail2ban/unban/", {
        method: "POST",
        body: JSON.stringify({ ip_address: ip, jail_name: jail }),
      }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const sync = useMutation({
    mutationFn: () => apiRequest("/firewall/fail2ban/sync/", { method: "POST", body: "{}" }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  function onCreateRule(e: FormEvent) {
    e.preventDefault();
    createRule.mutate();
  }

  function onBan(e: FormEvent) {
    e.preventDefault();
    banIp.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="text-sm text-cp-muted">
            Règles firewall et Fail2Ban — mode {overview?.provision_mode ?? "…"}.
          </p>
        </div>
        <button
          className="vz-btn-primary"
          type="button"
          onClick={() => sync.mutate()}
          disabled={sync.isPending}
        >
          Sync Fail2Ban
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Règles", value: overview?.rules ?? "—" },
          { label: "Appliquées", value: overview?.rules_applied ?? "—" },
          { label: "Jails", value: overview?.jails ?? "—" },
          { label: "Bans actifs", value: overview?.bans_active ?? "—" },
        ].map((card) => (
          <div key={card.label} className="vz-panel p-4">
            <p className="text-xs font-semibold uppercase text-cp-muted">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold text-cp-orange">{card.value}</p>
          </div>
        ))}
      </div>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          {error}
        </div>
      )}

      <form onSubmit={onCreateRule} className="vz-panel grid gap-3 p-4 md:grid-cols-6">
        <h2 className="md:col-span-6 text-sm font-semibold">Nouvelle règle</h2>
        <label className="text-sm md:col-span-2">
          Nom
          <input
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={ruleForm.name}
            onChange={(e) => setRuleForm((f) => ({ ...f, name: e.target.value }))}
            required
          />
        </label>
        <label className="text-sm">
          Action
          <select
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={ruleForm.action}
            onChange={(e) => setRuleForm((f) => ({ ...f, action: e.target.value }))}
          >
            <option value="allow">Allow</option>
            <option value="deny">Deny</option>
          </select>
        </label>
        <label className="text-sm">
          Proto
          <select
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={ruleForm.protocol}
            onChange={(e) => setRuleForm((f) => ({ ...f, protocol: e.target.value }))}
          >
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
            <option value="any">Any</option>
          </select>
        </label>
        <label className="text-sm">
          Port
          <input
            type="number"
            min={1}
            max={65535}
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={ruleForm.port_start}
            onChange={(e) => setRuleForm((f) => ({ ...f, port_start: Number(e.target.value) }))}
          />
        </label>
        <label className="text-sm">
          Source CIDR
          <input
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={ruleForm.source_cidr}
            onChange={(e) => setRuleForm((f) => ({ ...f, source_cidr: e.target.value }))}
            placeholder="optionnel"
          />
        </label>
        <label className="text-sm inline-flex items-center gap-2 pt-6 md:col-span-2">
          <input
            type="checkbox"
            checked={ruleForm.apply_now}
            onChange={(e) => setRuleForm((f) => ({ ...f, apply_now: e.target.checked }))}
          />
          Appliquer maintenant
        </label>
        <div className="flex items-end md:col-span-4">
          <button
            type="submit"
            className="rounded bg-cp-orange px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            disabled={createRule.isPending}
          >
            Ajouter la règle
          </button>
        </div>
      </form>

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-cp-canvas text-left text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Règle</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Port</th>
              <th className="px-3 py-2">État</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loadingRules && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Chargement…
                </td>
              </tr>
            )}
            {!loadingRules && rules.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Aucune règle.
                </td>
              </tr>
            )}
            {rules.map((r) => (
              <tr key={r.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2">
                  <div className="font-medium">{r.name}</div>
                  <div className="text-xs text-cp-muted">
                    {r.protocol}/{r.direction}
                    {r.source_cidr ? ` src=${r.source_cidr}` : ""}
                  </div>
                </td>
                <td className="px-3 py-2">{r.action}</td>
                <td className="px-3 py-2">{r.port_start ?? "—"}</td>
                <td className="px-3 py-2">
                  {r.is_applied ? "appliquée" : "en attente"}
                  {r.last_error && <div className="text-xs text-red-600">{r.last_error}</div>}
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    {!r.is_applied && (
                      <button
                        type="button"
                        className="text-xs text-cp-orange hover:underline"
                        onClick={() => applyRule.mutate(r.id)}
                      >
                        Appliquer
                      </button>
                    )}
                    <button
                      type="button"
                      className="text-xs text-red-600 hover:underline"
                      onClick={() => removeRule.mutate(r.id)}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="vz-panel overflow-x-auto">
          <div className="border-b border-cp-border px-4 py-3 text-sm font-semibold dark:border-ink-800">
            Jails Fail2Ban
          </div>
          <table className="min-w-full text-sm">
            <thead className="bg-cp-canvas text-left text-xs uppercase text-cp-muted dark:bg-ink-900">
              <tr>
                <th className="px-3 py-2">Jail</th>
                <th className="px-3 py-2">Bannis</th>
                <th className="px-3 py-2">Total</th>
              </tr>
            </thead>
            <tbody>
              {jails.map((j) => (
                <tr key={j.id} className="border-t border-cp-border dark:border-ink-800">
                  <td className="px-3 py-2 font-medium">{j.name}</td>
                  <td className="px-3 py-2">{j.currently_banned}</td>
                  <td className="px-3 py-2">{j.total_banned}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="space-y-3">
          <form onSubmit={onBan} className="vz-panel grid gap-3 p-4">
            <h2 className="text-sm font-semibold">Ban IP</h2>
            <label className="text-sm">
              Adresse IP
              <input
                className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
                value={banForm.ip_address}
                onChange={(e) => setBanForm((f) => ({ ...f, ip_address: e.target.value }))}
                required
              />
            </label>
            <label className="text-sm">
              Jail
              <input
                className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
                value={banForm.jail_name}
                onChange={(e) => setBanForm((f) => ({ ...f, jail_name: e.target.value }))}
              />
            </label>
            <label className="text-sm">
              Raison
              <input
                className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
                value={banForm.reason}
                onChange={(e) => setBanForm((f) => ({ ...f, reason: e.target.value }))}
              />
            </label>
            <button
              type="submit"
              className="rounded bg-cp-orange px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
              disabled={banIp.isPending}
            >
              Bannir
            </button>
          </form>

          <div className="vz-panel overflow-x-auto">
            <div className="border-b border-cp-border px-4 py-3 text-sm font-semibold dark:border-ink-800">
              Bans actifs
            </div>
            <table className="min-w-full text-sm">
              <thead className="bg-cp-canvas text-left text-xs uppercase text-cp-muted dark:bg-ink-900">
                <tr>
                  <th className="px-3 py-2">IP</th>
                  <th className="px-3 py-2">Jail</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {bans.length === 0 && (
                  <tr>
                    <td className="px-3 py-4 text-cp-muted" colSpan={3}>
                      Aucun ban actif.
                    </td>
                  </tr>
                )}
                {bans.map((b) => (
                  <tr key={b.id} className="border-t border-cp-border dark:border-ink-800">
                    <td className="px-3 py-2 font-medium">{b.ip_address}</td>
                    <td className="px-3 py-2">{b.jail_name}</td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        className="text-xs text-cp-orange hover:underline"
                        onClick={() => unbanIp.mutate({ ip: b.ip_address, jail: b.jail_name })}
                      >
                        Unban
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
