import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Plus,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Unlock,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot, Tabs } from "@/components/ui/PageChrome";

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

function formatWhen(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("fr-FR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatBanDuration(seconds: number) {
  if (!seconds || seconds <= 0) return "permanent";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h`;
  return `${Math.round(seconds / 86400)} j`;
}

const emptyRule = {
  name: "",
  action: "allow",
  protocol: "tcp",
  port_start: 443,
  source_cidr: "",
  apply_now: true,
};

const emptyBan = {
  ip_address: "",
  jail_name: "sshd",
  reason: "",
};

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
  const { data: jails = [], isLoading: loadingJails } = useQuery({
    queryKey: ["firewall-jails"],
    queryFn: () => apiRequest<JailItem[]>("/firewall/fail2ban/jails/"),
  });
  const { data: bans = [], isLoading: loadingBans } = useQuery({
    queryKey: ["firewall-bans"],
    queryFn: () => apiRequest<BanItem[]>("/firewall/fail2ban/bans/"),
  });

  const [ruleForm, setRuleForm] = useState(emptyRule);
  const [banForm, setBanForm] = useState(emptyBan);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("rules");
  const [ruleOpen, setRuleOpen] = useState(false);
  const [banOpen, setBanOpen] = useState(false);

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
      setRuleForm(emptyRule);
      setError(null);
      invalidate();
      setRuleOpen(false);
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
      setBanForm(emptyBan);
      setError(null);
      invalidate();
      setBanOpen(false);
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

  const modeLabel =
    overview?.provision_mode === "live"
      ? "Mode réel"
      : overview?.provision_mode
        ? `Mode ${overview.provision_mode}`
        : "…";

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Ouvrez ou fermez des ports, et bloquez les IP abusives avec Fail2Ban."
        stats={[
          { label: "Règles", value: overview?.rules ?? "—" },
          { label: "Appliquées", value: overview?.rules_applied ?? "—" },
          { label: "Protections", value: overview?.jails ?? "—" },
          { label: "IP bannies", value: overview?.bans_active ?? "—" },
        ]}
        actions={
          <>
            <button
              type="button"
              className="vz-btn-ghost"
              onClick={() => sync.mutate()}
              disabled={sync.isPending}
            >
              <RefreshCw className={`h-4 w-4 ${sync.isPending ? "animate-spin" : ""}`} />
              Sync Fail2Ban
            </button>
            {tab === "bans" ? (
              <button type="button" className="vz-btn-primary" onClick={() => setBanOpen(true)}>
                <Ban className="h-4 w-4" />
                Bannir une IP
              </button>
            ) : (
              <button type="button" className="vz-btn-primary" onClick={() => setRuleOpen(true)}>
                <Plus className="h-4 w-4" />
                Ajouter une règle
              </button>
            )}
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2 text-xs text-cp-muted">
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-cp-border/70 bg-white px-2.5 py-1.5 dark:border-ink-700 dark:bg-ink-950">
          <Shield className="h-3.5 w-3.5 text-cp-orange" />
          {modeLabel}
        </span>
        {(overview?.bans_active ?? 0) > 0 && (
          <span className="inline-flex items-center gap-1.5 rounded-lg bg-rose-50 px-2.5 py-1.5 font-medium text-rose-700 ring-1 ring-inset ring-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-900">
            <ShieldAlert className="h-3.5 w-3.5" />
            {overview?.bans_active} IP actuellement bloquée
            {(overview?.bans_active ?? 0) > 1 ? "s" : ""}
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {error}
        </div>
      )}

      <div className="vz-panel overflow-hidden">
        <Tabs
          tabs={[
            { id: "rules", label: "Règles", count: rules.length, icon: <Shield className="h-3.5 w-3.5" /> },
            {
              id: "jails",
              label: "Protections",
              count: jails.length,
              icon: <ShieldCheck className="h-3.5 w-3.5" />,
            },
            {
              id: "bans",
              label: "IP bannies",
              count: bans.length,
              icon: <Ban className="h-3.5 w-3.5" />,
            },
          ]}
          active={tab}
          onChange={setTab}
        />

        {tab === "rules" && (
          <div>
            {loadingRules ? (
              <p className="px-4 py-10 text-center text-sm text-cp-muted">Chargement…</p>
            ) : rules.length === 0 ? (
              <EmptyState
                icon={<Shield className="h-5 w-5" />}
                message="Aucune règle firewall. Ajoutez une règle pour autoriser ou refuser un port."
                action={
                  <button type="button" className="vz-btn-primary" onClick={() => setRuleOpen(true)}>
                    <Plus className="h-4 w-4" />
                    Ajouter une règle
                  </button>
                }
              />
            ) : (
              <ul className="divide-y divide-cp-border dark:divide-ink-800">
                {rules.map((r) => (
                  <li
                    key={r.id}
                    className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold text-cp-text">{r.name}</p>
                        <span
                          className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${
                            r.action === "allow"
                              ? "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900"
                              : "bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-900"
                          }`}
                        >
                          {r.action === "allow" ? "Autoriser" : "Refuser"}
                        </span>
                        <StatusDot
                          status={r.is_applied ? "active" : "inactive"}
                          label={r.is_applied ? "Appliquée" : "En attente"}
                        />
                      </div>
                      <p className="text-sm text-cp-muted">
                        {(r.protocol || "any").toUpperCase()}
                        {r.port_start != null ? ` · port ${r.port_start}` : ""}
                        {r.port_end && r.port_end !== r.port_start ? `–${r.port_end}` : ""}
                        {r.source_cidr ? ` · source ${r.source_cidr}` : " · toutes sources"}
                        {r.direction ? ` · ${r.direction}` : ""}
                      </p>
                      {r.last_error ? (
                        <p className="text-xs text-rose-600 dark:text-rose-400">{r.last_error}</p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {!r.is_applied && (
                        <button
                          type="button"
                          className="vz-btn-ghost !py-1.5 text-xs"
                          onClick={() => applyRule.mutate(r.id)}
                          disabled={applyRule.isPending}
                        >
                          Appliquer
                        </button>
                      )}
                      <IconAction
                        label={`Supprimer ${r.name}`}
                        danger
                        onClick={() => {
                          if (window.confirm(`Supprimer la règle « ${r.name} » ?`)) {
                            removeRule.mutate(r.id);
                          }
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </IconAction>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {tab === "jails" && (
          <div>
            {loadingJails ? (
              <p className="px-4 py-10 text-center text-sm text-cp-muted">Chargement…</p>
            ) : jails.length === 0 ? (
              <EmptyState
                icon={<ShieldCheck className="h-5 w-5" />}
                message="Aucune protection Fail2Ban détectée. Lancez une synchronisation."
                action={
                  <button
                    type="button"
                    className="vz-btn-primary"
                    onClick={() => sync.mutate()}
                    disabled={sync.isPending}
                  >
                    <RefreshCw className="h-4 w-4" />
                    Synchroniser
                  </button>
                }
              />
            ) : (
              <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
                {jails.map((j) => (
                  <div
                    key={j.id}
                    className="rounded-xl border border-cp-border/70 bg-cp-canvas/40 p-3.5 dark:border-ink-700 dark:bg-ink-900/40"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-semibold text-cp-text">{j.name}</p>
                        <StatusDot
                          status={j.is_enabled ? "active" : "inactive"}
                          label={j.is_enabled ? "Activée" : "Désactivée"}
                        />
                      </div>
                      <span className="rounded-lg bg-white px-2 py-1 text-lg font-semibold tabular-nums text-cp-orange shadow-sm dark:bg-ink-950">
                        {j.currently_banned}
                      </span>
                    </div>
                    <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-cp-muted">
                      <div>
                        <dt>Bannis maintenant</dt>
                        <dd className="font-medium text-cp-text">{j.currently_banned}</dd>
                      </div>
                      <div>
                        <dt>Total historique</dt>
                        <dd className="font-medium text-cp-text">{j.total_banned}</dd>
                      </div>
                      <div>
                        <dt>Tentatives max</dt>
                        <dd className="font-medium text-cp-text">{j.max_retry}</dd>
                      </div>
                      <div>
                        <dt>Durée ban</dt>
                        <dd className="font-medium text-cp-text">{formatBanDuration(j.ban_time)}</dd>
                      </div>
                    </dl>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "bans" && (
          <div>
            {loadingBans ? (
              <p className="px-4 py-10 text-center text-sm text-cp-muted">Chargement…</p>
            ) : bans.length === 0 ? (
              <EmptyState
                icon={<Unlock className="h-5 w-5" />}
                message="Aucune IP bannie actuellement."
                action={
                  <button type="button" className="vz-btn-primary" onClick={() => setBanOpen(true)}>
                    <Ban className="h-4 w-4" />
                    Bannir une IP
                  </button>
                }
              />
            ) : (
              <ul className="divide-y divide-cp-border dark:divide-ink-800">
                {bans.map((b) => (
                  <li
                    key={b.id}
                    className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0 space-y-1">
                      <p className="font-mono text-sm font-semibold text-cp-text">{b.ip_address}</p>
                      <p className="text-sm text-cp-muted">
                        Protection {b.jail_name}
                        {b.reason ? ` · ${b.reason}` : ""}
                      </p>
                      <p className="text-[11px] text-cp-muted">{formatWhen(b.banned_at)}</p>
                    </div>
                    <button
                      type="button"
                      className="vz-btn-ghost !py-1.5 text-xs"
                      onClick={() => unbanIp.mutate({ ip: b.ip_address, jail: b.jail_name })}
                      disabled={unbanIp.isPending}
                    >
                      <Unlock className="h-3.5 w-3.5" />
                      Débannir
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {ruleOpen && (
        <Modal title="Nouvelle règle firewall" onClose={() => setRuleOpen(false)} wide>
          <form onSubmit={onCreateRule} className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm sm:col-span-2">
              <span className="mb-1 block font-medium">Nom</span>
              <input
                className="vz-input w-full"
                placeholder="Ex. HTTPS public"
                value={ruleForm.name}
                onChange={(e) => setRuleForm((f) => ({ ...f, name: e.target.value }))}
                required
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Action</span>
              <select
                className="vz-input w-full"
                value={ruleForm.action}
                onChange={(e) => setRuleForm((f) => ({ ...f, action: e.target.value }))}
              >
                <option value="allow">Autoriser</option>
                <option value="deny">Refuser</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Protocole</span>
              <select
                className="vz-input w-full"
                value={ruleForm.protocol}
                onChange={(e) => setRuleForm((f) => ({ ...f, protocol: e.target.value }))}
              >
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
                <option value="any">Tous</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Port</span>
              <input
                type="number"
                min={1}
                max={65535}
                className="vz-input w-full"
                value={ruleForm.port_start}
                onChange={(e) => setRuleForm((f) => ({ ...f, port_start: Number(e.target.value) }))}
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Source (CIDR)</span>
              <input
                className="vz-input w-full"
                placeholder="Optionnel — ex. 203.0.113.0/24"
                value={ruleForm.source_cidr}
                onChange={(e) => setRuleForm((f) => ({ ...f, source_cidr: e.target.value }))}
              />
            </label>
            <label className="inline-flex items-center gap-2 text-sm sm:col-span-2">
              <input
                type="checkbox"
                className="accent-cp-orange"
                checked={ruleForm.apply_now}
                onChange={(e) => setRuleForm((f) => ({ ...f, apply_now: e.target.checked }))}
              />
              Appliquer immédiatement
            </label>
            <div className="flex justify-end gap-2 sm:col-span-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setRuleOpen(false)}>
                Annuler
              </button>
              <button className="vz-btn-primary" disabled={createRule.isPending}>
                {createRule.isPending ? "Ajout…" : "Ajouter"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {banOpen && (
        <Modal title="Bannir une adresse IP" onClose={() => setBanOpen(false)}>
          <form onSubmit={onBan} className="space-y-3">
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Adresse IP</span>
              <input
                className="vz-input w-full font-mono"
                placeholder="203.0.113.10"
                value={banForm.ip_address}
                onChange={(e) => setBanForm((f) => ({ ...f, ip_address: e.target.value }))}
                required
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Protection (jail)</span>
              <input
                className="vz-input w-full"
                list="jail-options"
                value={banForm.jail_name}
                onChange={(e) => setBanForm((f) => ({ ...f, jail_name: e.target.value }))}
              />
              <datalist id="jail-options">
                {jails.map((j) => (
                  <option key={j.id} value={j.name} />
                ))}
              </datalist>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Raison</span>
              <input
                className="vz-input w-full"
                placeholder="Optionnel"
                value={banForm.reason}
                onChange={(e) => setBanForm((f) => ({ ...f, reason: e.target.value }))}
              />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setBanOpen(false)}>
                Annuler
              </button>
              <button className="vz-btn-primary" disabled={banIp.isPending}>
                {banIp.isPending ? "Ban…" : "Bannir"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
