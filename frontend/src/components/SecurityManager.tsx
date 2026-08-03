import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

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
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-cp-muted">
          Politique MDP, lockout login, allow/blocklist IP panel (distinct du Firewall OS).
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "2FA actifs", value: overview?.users_2fa_enabled ?? "—" },
          { label: "Lockouts", value: overview?.lockouts_active ?? "—" },
          { label: "Échecs 24h", value: overview?.login_failures_24h ?? "—" },
          { label: "Règles IP", value: overview?.ip_rules ?? "—" },
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

      <form onSubmit={onPolicy} className="vz-panel grid gap-3 p-4 md:grid-cols-4">
        <h2 className="md:col-span-4 text-sm font-semibold">Politique</h2>
        <label className="text-sm">
          Longueur min MDP
          <input
            type="number"
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={policyForm.password_min_length}
            onChange={(e) => setPolicyForm((f) => ({ ...f, password_min_length: Number(e.target.value) }))}
          />
        </label>
        <label className="text-sm">
          Tentatives max
          <input
            type="number"
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={policyForm.lockout_max_attempts}
            onChange={(e) => setPolicyForm((f) => ({ ...f, lockout_max_attempts: Number(e.target.value) }))}
          />
        </label>
        <label className="text-sm">
          Fenêtre (min)
          <input
            type="number"
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={policyForm.lockout_window_minutes}
            onChange={(e) => setPolicyForm((f) => ({ ...f, lockout_window_minutes: Number(e.target.value) }))}
          />
        </label>
        <label className="text-sm">
          Durée lockout (min)
          <input
            type="number"
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={policyForm.lockout_duration_minutes}
            onChange={(e) => setPolicyForm((f) => ({ ...f, lockout_duration_minutes: Number(e.target.value) }))}
          />
        </label>
        <label className="text-sm">
          Mode IP
          <select
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={policyForm.ip_mode}
            onChange={(e) => setPolicyForm((f) => ({ ...f, ip_mode: e.target.value }))}
          >
            <option value="off">Off</option>
            <option value="allowlist">Allowlist</option>
            <option value="blocklist">Blocklist</option>
          </select>
        </label>
        <label className="text-sm inline-flex items-center gap-2 pt-6">
          <input
            type="checkbox"
            checked={policyForm.require_digit}
            onChange={(e) => setPolicyForm((f) => ({ ...f, require_digit: e.target.checked }))}
          />
          Chiffre requis
        </label>
        <label className="text-sm inline-flex items-center gap-2 pt-6">
          <input
            type="checkbox"
            checked={policyForm.require_uppercase}
            onChange={(e) => setPolicyForm((f) => ({ ...f, require_uppercase: e.target.checked }))}
          />
          Majuscule
        </label>
        <label className="text-sm inline-flex items-center gap-2 pt-6">
          <input
            type="checkbox"
            checked={policyForm.force_2fa_admins}
            onChange={(e) => setPolicyForm((f) => ({ ...f, force_2fa_admins: e.target.checked }))}
          />
          2FA obligatoire WHM
        </label>
        <div className="md:col-span-4">
          <button type="submit" className="rounded bg-cp-orange px-3 py-2 text-sm font-medium text-white">
            Enregistrer la politique
          </button>
        </div>
      </form>

      <form onSubmit={onIp} className="vz-panel grid gap-3 p-4 md:grid-cols-4">
        <h2 className="md:col-span-4 text-sm font-semibold">Règle IP panel</h2>
        <label className="text-sm md:col-span-2">
          CIDR
          <input
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={ipForm.cidr}
            onChange={(e) => setIpForm((f) => ({ ...f, cidr: e.target.value }))}
            placeholder="203.0.113.0/24"
            required
          />
        </label>
        <label className="text-sm">
          Type
          <select
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={ipForm.list_type}
            onChange={(e) => setIpForm((f) => ({ ...f, list_type: e.target.value }))}
          >
            <option value="block">Block</option>
            <option value="allow">Allow</option>
          </select>
        </label>
        <div className="flex items-end">
          <button type="submit" className="w-full rounded border border-cp-border px-3 py-2 text-sm dark:border-ink-700">
            Ajouter
          </button>
        </div>
        <div className="md:col-span-4 overflow-x-auto">
          <table className="min-w-full text-sm">
            <tbody>
              {ipRules.map((r) => (
                <tr key={r.id} className="border-t border-cp-border dark:border-ink-800">
                  <td className="px-2 py-2 font-medium">{r.cidr}</td>
                  <td className="px-2 py-2">{r.list_type}</td>
                  <td className="px-2 py-2">
                    <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => removeIp.mutate(r.id)}>
                      Supprimer
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </form>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="vz-panel overflow-x-auto">
          <div className="border-b border-cp-border px-4 py-3 text-sm font-semibold dark:border-ink-800">Lockouts</div>
          <table className="min-w-full text-sm">
            <tbody>
              {lockouts.length === 0 && (
                <tr>
                  <td className="px-3 py-4 text-cp-muted">Aucun lockout.</td>
                </tr>
              )}
              {lockouts.map((l) => (
                <tr key={l.id} className="border-t border-cp-border dark:border-ink-800">
                  <td className="px-3 py-2">
                    <div className="font-medium">{l.key}</div>
                    <div className="text-xs text-cp-muted">{l.attempts} tentatives</div>
                  </td>
                  <td className="px-3 py-2">
                    <button type="button" className="text-xs text-cp-orange hover:underline" onClick={() => unlock.mutate(l.key)}>
                      Déverrouiller
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="vz-panel overflow-x-auto">
          <div className="border-b border-cp-border px-4 py-3 text-sm font-semibold dark:border-ink-800">
            Tentatives récentes
          </div>
          <table className="min-w-full text-sm">
            <tbody>
              {attempts.slice(0, 15).map((a) => (
                <tr key={a.id} className="border-t border-cp-border dark:border-ink-800">
                  <td className="px-3 py-2">
                    <div className="font-medium">{a.email || "—"}</div>
                    <div className="text-xs text-cp-muted">{a.ip_address}</div>
                  </td>
                  <td className="px-3 py-2">{a.success ? "ok" : "échec"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
