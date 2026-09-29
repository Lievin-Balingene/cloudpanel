import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  KeyRound,
  Plus,
  Shield,
  Trash2,
  Unlock,
  UserX,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot, Tabs } from "@/components/ui/PageChrome";

interface SecurityOverview {
  policy: {
    password_min_length: number;
    require_uppercase: boolean;
    require_digit: boolean;
    require_special: boolean;
    lockout_max_attempts: number;
    lockout_window_minutes: number;
    lockout_duration_minutes: number;
    ip_mode: string;
    force_2fa_admins: boolean;
  };
  users_total: number;
  users_2fa_enabled: number;
  users_must_change_password: number;
  ip_rules: number;
  lockouts_active: number;
  login_failures_24h: number;
  login_success_24h: number;
}

interface IpRule {
  id: number;
  cidr: string;
  list_type: string;
  is_active: boolean;
  notes: string;
}

interface Lockout {
  id: number;
  key: string;
  attempts: number;
  locked_until: string | null;
}

interface Attempt {
  id: number;
  email: string;
  ip_address: string | null;
  success: boolean;
  message: string;
  created_at: string;
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

const IP_MODE_LABELS: Record<string, string> = {
  off: "Désactivé",
  allowlist: "Liste blanche",
  blocklist: "Liste noire",
};

export function SecurityManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["security-overview"],
    queryFn: () => apiRequest<SecurityOverview>("/security/overview/"),
  });
  const { data: policy } = useQuery({
    queryKey: ["security-policy"],
    queryFn: () => apiRequest<SecurityOverview["policy"] & { id: number }>("/security/policy/"),
  });
  const { data: ipRules = [] } = useQuery({
    queryKey: ["security-ip-rules"],
    queryFn: () => apiRequest<IpRule[]>("/security/ip-rules/"),
  });
  const { data: lockouts = [] } = useQuery({
    queryKey: ["security-lockouts"],
    queryFn: () => apiRequest<Lockout[]>("/security/lockouts/"),
  });
  const { data: attempts = [] } = useQuery({
    queryKey: ["security-attempts"],
    queryFn: () => apiRequest<Attempt[]>("/security/attempts/"),
  });

  const [policyForm, setPolicyForm] = useState({
    password_min_length: 10,
    require_uppercase: false,
    require_digit: true,
    require_special: false,
    lockout_max_attempts: 5,
    lockout_window_minutes: 15,
    lockout_duration_minutes: 30,
    ip_mode: "off",
    force_2fa_admins: false,
  });
  const [ipForm, setIpForm] = useState({ cidr: "", list_type: "block", notes: "" });
  const [error, setError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);
  const [tab, setTab] = useState("policy");
  const [ipOpen, setIpOpen] = useState(false);

  useEffect(() => {
    if (!policy) return;
    setPolicyForm({
      password_min_length: policy.password_min_length,
      require_uppercase: policy.require_uppercase,
      require_digit: policy.require_digit,
      require_special: policy.require_special,
      lockout_max_attempts: policy.lockout_max_attempts,
      lockout_window_minutes: policy.lockout_window_minutes,
      lockout_duration_minutes: policy.lockout_duration_minutes,
      ip_mode: policy.ip_mode,
      force_2fa_admins: policy.force_2fa_admins,
    });
  }, [policy]);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["security-overview"] });
    void qc.invalidateQueries({ queryKey: ["security-policy"] });
    void qc.invalidateQueries({ queryKey: ["security-ip-rules"] });
    void qc.invalidateQueries({ queryKey: ["security-lockouts"] });
    void qc.invalidateQueries({ queryKey: ["security-attempts"] });
  };

  const savePolicy = useMutation({
    mutationFn: () =>
      apiRequest("/security/policy/", {
        method: "PATCH",
        body: JSON.stringify(policyForm),
      }),
    onSuccess: () => {
      setError(null);
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 2000);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const addIp = useMutation({
    mutationFn: () =>
      apiRequest("/security/ip-rules/", {
        method: "POST",
        body: JSON.stringify(ipForm),
      }),
    onSuccess: () => {
      setIpForm({ cidr: "", list_type: "block", notes: "" });
      invalidate();
      setIpOpen(false);
    },
    onError: (err: Error) => setError(err.message),
  });

  const removeIp = useMutation({
    mutationFn: (id: number) => apiRequest(`/security/ip-rules/${id}/`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const unlock = useMutation({
    mutationFn: (key: string) =>
      apiRequest("/security/unlock/", { method: "POST", body: JSON.stringify({ key }) }),
    onSuccess: invalidate,
  });

  function onPolicy(e: FormEvent) {
    e.preventDefault();
    savePolicy.mutate();
  }

  function onIp(e: FormEvent) {
    e.preventDefault();
    addIp.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Mot de passe, double authentification, verrouillages et contrôle d’accès IP au panneau."
        stats={[
          { label: "2FA actifs", value: overview?.users_2fa_enabled ?? "—" },
          { label: "Verrouillages", value: overview?.lockouts_active ?? "—" },
          { label: "Échecs 24 h", value: overview?.login_failures_24h ?? "—" },
          { label: "Règles IP", value: overview?.ip_rules ?? "—" },
        ]}
        actions={
          tab === "ip" ? (
            <button type="button" className="vz-btn-primary" onClick={() => setIpOpen(true)}>
              <Plus className="h-4 w-4" />
              Ajouter une IP
            </button>
          ) : undefined
        }
      />

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {error}
        </div>
      )}

      <div className="vz-panel overflow-hidden">
        <Tabs
          tabs={[
            { id: "policy", label: "Politique", icon: <KeyRound className="h-3.5 w-3.5" /> },
            {
              id: "ip",
              label: "Accès IP",
              count: ipRules.length,
              icon: <Shield className="h-3.5 w-3.5" />,
            },
            {
              id: "lockouts",
              label: "Verrouillages",
              count: lockouts.length,
              icon: <UserX className="h-3.5 w-3.5" />,
            },
            { id: "attempts", label: "Connexions", icon: <Unlock className="h-3.5 w-3.5" /> },
          ]}
          active={tab}
          onChange={setTab}
        />

        {tab === "policy" && (
          <form onSubmit={onPolicy} className="space-y-5 p-4 sm:p-5">
            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-cp-text">Mot de passe</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <label className="block text-sm sm:col-span-1">
                  <span className="mb-1 block font-medium text-cp-muted">Longueur minimale</span>
                  <input
                    type="number"
                    min={6}
                    className="vz-input w-full"
                    value={policyForm.password_min_length}
                    onChange={(e) =>
                      setPolicyForm((f) => ({
                        ...f,
                        password_min_length: Number(e.target.value),
                      }))
                    }
                  />
                </label>
                <label className="flex items-center gap-2 rounded-lg border border-cp-border/70 bg-cp-canvas/40 px-3 py-2 text-sm dark:border-ink-700 dark:bg-ink-900/40">
                  <input
                    type="checkbox"
                    className="accent-cp-orange"
                    checked={policyForm.require_digit}
                    onChange={(e) =>
                      setPolicyForm((f) => ({ ...f, require_digit: e.target.checked }))
                    }
                  />
                  Chiffre requis
                </label>
                <label className="flex items-center gap-2 rounded-lg border border-cp-border/70 bg-cp-canvas/40 px-3 py-2 text-sm dark:border-ink-700 dark:bg-ink-900/40">
                  <input
                    type="checkbox"
                    className="accent-cp-orange"
                    checked={policyForm.require_uppercase}
                    onChange={(e) =>
                      setPolicyForm((f) => ({ ...f, require_uppercase: e.target.checked }))
                    }
                  />
                  Majuscule requise
                </label>
                <label className="flex items-center gap-2 rounded-lg border border-cp-border/70 bg-cp-canvas/40 px-3 py-2 text-sm dark:border-ink-700 dark:bg-ink-900/40">
                  <input
                    type="checkbox"
                    className="accent-cp-orange"
                    checked={policyForm.require_special}
                    onChange={(e) =>
                      setPolicyForm((f) => ({ ...f, require_special: e.target.checked }))
                    }
                  />
                  Caractère spécial
                </label>
              </div>
            </section>

            <section className="space-y-3 border-t border-cp-border pt-5 dark:border-ink-800">
              <h2 className="text-sm font-semibold text-cp-text">Verrouillage après échecs</h2>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="block text-sm">
                  <span className="mb-1 block font-medium text-cp-muted">Tentatives max</span>
                  <input
                    type="number"
                    min={1}
                    className="vz-input w-full"
                    value={policyForm.lockout_max_attempts}
                    onChange={(e) =>
                      setPolicyForm((f) => ({
                        ...f,
                        lockout_max_attempts: Number(e.target.value),
                      }))
                    }
                  />
                </label>
                <label className="block text-sm">
                  <span className="mb-1 block font-medium text-cp-muted">Fenêtre (min)</span>
                  <input
                    type="number"
                    min={1}
                    className="vz-input w-full"
                    value={policyForm.lockout_window_minutes}
                    onChange={(e) =>
                      setPolicyForm((f) => ({
                        ...f,
                        lockout_window_minutes: Number(e.target.value),
                      }))
                    }
                  />
                </label>
                <label className="block text-sm">
                  <span className="mb-1 block font-medium text-cp-muted">Durée du blocage (min)</span>
                  <input
                    type="number"
                    min={1}
                    className="vz-input w-full"
                    value={policyForm.lockout_duration_minutes}
                    onChange={(e) =>
                      setPolicyForm((f) => ({
                        ...f,
                        lockout_duration_minutes: Number(e.target.value),
                      }))
                    }
                  />
                </label>
              </div>
            </section>

            <section className="space-y-3 border-t border-cp-border pt-5 dark:border-ink-800">
              <h2 className="text-sm font-semibold text-cp-text">Accès & 2FA</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm">
                  <span className="mb-1 block font-medium text-cp-muted">Filtrage IP</span>
                  <select
                    className="vz-input w-full"
                    value={policyForm.ip_mode}
                    onChange={(e) => setPolicyForm((f) => ({ ...f, ip_mode: e.target.value }))}
                  >
                    <option value="off">Désactivé</option>
                    <option value="allowlist">Liste blanche (autoriser seulement)</option>
                    <option value="blocklist">Liste noire (bloquer)</option>
                  </select>
                </label>
                <label className="flex items-center gap-2 rounded-lg border border-cp-border/70 bg-cp-canvas/40 px-3 py-2 text-sm dark:border-ink-700 dark:bg-ink-900/40 sm:mt-6">
                  <input
                    type="checkbox"
                    className="accent-cp-orange"
                    checked={policyForm.force_2fa_admins}
                    onChange={(e) =>
                      setPolicyForm((f) => ({ ...f, force_2fa_admins: e.target.checked }))
                    }
                  />
                  2FA obligatoire pour les admins WHM
                </label>
              </div>
            </section>

            <div className="flex flex-wrap items-center gap-3 border-t border-cp-border pt-4 dark:border-ink-800">
              <button type="submit" className="vz-btn-primary" disabled={savePolicy.isPending}>
                {savePolicy.isPending ? "Enregistrement…" : "Enregistrer"}
              </button>
              {savedFlash && (
                <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
                  Politique enregistrée
                </span>
              )}
            </div>
          </form>
        )}

        {tab === "ip" && (
          <div>
            <div className="border-b border-cp-border bg-cp-canvas/40 px-4 py-2.5 text-xs text-cp-muted dark:border-ink-800 dark:bg-ink-900/40">
              Mode actuel :{" "}
              <strong className="text-cp-text">
                {IP_MODE_LABELS[policyForm.ip_mode] || policyForm.ip_mode}
              </strong>
              {policyForm.ip_mode === "off"
                ? " — les règles ci-dessous ne s’appliquent pas tant que le mode est désactivé."
                : null}
            </div>
            {ipRules.length === 0 ? (
              <EmptyState
                icon={<Shield className="h-5 w-5" />}
                message="Aucune règle IP. Ajoutez une adresse ou un réseau à autoriser ou bloquer."
                action={
                  <button type="button" className="vz-btn-primary" onClick={() => setIpOpen(true)}>
                    <Plus className="h-4 w-4" />
                    Ajouter une IP
                  </button>
                }
              />
            ) : (
              <ul className="divide-y divide-cp-border dark:divide-ink-800">
                {ipRules.map((r) => (
                  <li
                    key={r.id}
                    className="flex flex-col gap-2 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-mono text-sm font-semibold text-cp-text">{r.cidr}</p>
                        <span
                          className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${
                            r.list_type === "allow"
                              ? "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900"
                              : "bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-900"
                          }`}
                        >
                          {r.list_type === "allow" ? "Autoriser" : "Bloquer"}
                        </span>
                        <StatusDot
                          status={r.is_active ? "active" : "inactive"}
                          label={r.is_active ? "Active" : "Inactive"}
                        />
                      </div>
                      {r.notes ? <p className="mt-1 text-xs text-cp-muted">{r.notes}</p> : null}
                    </div>
                    <IconAction
                      label={`Supprimer ${r.cidr}`}
                      danger
                      onClick={() => {
                        if (window.confirm(`Supprimer la règle ${r.cidr} ?`)) {
                          removeIp.mutate(r.id);
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </IconAction>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {tab === "lockouts" && (
          <div>
            {lockouts.length === 0 ? (
              <EmptyState
                icon={<Unlock className="h-5 w-5" />}
                message="Aucun compte ou IP verrouillé pour le moment."
              />
            ) : (
              <ul className="divide-y divide-cp-border dark:divide-ink-800">
                {lockouts.map((l) => (
                  <li
                    key={l.id}
                    className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="font-semibold text-cp-text">{l.key}</p>
                      <p className="text-sm text-cp-muted">
                        {l.attempts} tentative{l.attempts > 1 ? "s" : ""}
                        {l.locked_until ? ` · jusqu’à ${formatWhen(l.locked_until)}` : ""}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="vz-btn-ghost !py-1.5 text-xs"
                      onClick={() => unlock.mutate(l.key)}
                      disabled={unlock.isPending}
                    >
                      <Unlock className="h-3.5 w-3.5" />
                      Déverrouiller
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {tab === "attempts" && (
          <div>
            {attempts.length === 0 ? (
              <EmptyState
                icon={<KeyRound className="h-5 w-5" />}
                message="Aucune tentative de connexion récente."
              />
            ) : (
              <ul className="divide-y divide-cp-border dark:divide-ink-800">
                {attempts.slice(0, 30).map((a) => (
                  <li
                    key={a.id}
                    className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-cp-text">{a.email || "—"}</p>
                      <p className="text-xs text-cp-muted">
                        {a.ip_address || "IP inconnue"} · {formatWhen(a.created_at)}
                        {a.message ? ` · ${a.message}` : ""}
                      </p>
                    </div>
                    <StatusDot
                      status={a.success ? "ok" : "error"}
                      label={a.success ? "Réussie" : "Échec"}
                    />
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {ipOpen && (
        <Modal title="Ajouter une règle IP" onClose={() => setIpOpen(false)}>
          <form onSubmit={onIp} className="space-y-3">
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Adresse / réseau (CIDR)</span>
              <input
                className="vz-input w-full font-mono"
                value={ipForm.cidr}
                onChange={(e) => setIpForm((f) => ({ ...f, cidr: e.target.value }))}
                placeholder="203.0.113.0/24"
                required
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Action</span>
              <select
                className="vz-input w-full"
                value={ipForm.list_type}
                onChange={(e) => setIpForm((f) => ({ ...f, list_type: e.target.value }))}
              >
                <option value="block">Bloquer</option>
                <option value="allow">Autoriser</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Note</span>
              <input
                className="vz-input w-full"
                value={ipForm.notes}
                onChange={(e) => setIpForm((f) => ({ ...f, notes: e.target.value }))}
                placeholder="Optionnel"
              />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setIpOpen(false)}>
                Annuler
              </button>
              <button className="vz-btn-primary" disabled={addIp.isPending}>
                {addIp.isPending ? "Ajout…" : "Ajouter"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
