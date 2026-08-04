import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, RefreshCw, ToggleLeft, ToggleRight, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { PageHeader, StatusDot, Tabs } from "@/components/ui/PageChrome";

interface MonitoringOverview {
  rules: number;
  rules_active: number;
  events_open: number;
  events_acknowledged: number;
  events_total: number;
  metrics: {
    cpu_percent: number;
    ram_percent: number;
    disk_percent: number;
    load_1: number | null;
    services: Record<string, boolean>;
  };
  cooldown_default: number;
}

interface AlertRuleItem {
  id: number;
  name: string;
  metric: string;
  operator: string;
  threshold: number;
  service_name: string;
  severity: string;
  cooldown_minutes: number;
  notify_email: boolean;
  recipients: string;
  is_active: boolean;
  last_triggered_at: string | null;
}

interface AlertEventItem {
  id: number;
  rule: number;
  rule_name: string;
  rule_metric: string;
  rule_severity: string;
  status: string;
  metric_value: number | null;
  message: string;
  notified: boolean;
  created_at: string;
}

export function MonitoringManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["monitoring-overview"],
    queryFn: () => apiRequest<MonitoringOverview>("/monitoring/overview/"),
    refetchInterval: 15000,
  });
  const { data: rules = [], isLoading: loadingRules } = useQuery({
    queryKey: ["monitoring-rules"],
    queryFn: () => apiRequest<AlertRuleItem[]>("/monitoring/rules/"),
  });
  const { data: events = [], isLoading: loadingEvents } = useQuery({
    queryKey: ["monitoring-events"],
    queryFn: () => apiRequest<AlertEventItem[]>("/monitoring/events/"),
    refetchInterval: 15000,
  });

  const [form, setForm] = useState({
    name: "",
    metric: "cpu_percent",
    operator: "gte",
    threshold: 90,
    service_name: "",
    severity: "warning",
    cooldown_minutes: 30,
    notify_email: true,
    recipients: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("thresholds");
  const [createOpen, setCreateOpen] = useState(false);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["monitoring-overview"] });
    void qc.invalidateQueries({ queryKey: ["monitoring-rules"] });
    void qc.invalidateQueries({ queryKey: ["monitoring-events"] });
  };

  const create = useMutation({
    mutationFn: () =>
      apiRequest("/monitoring/rules/", {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: () => {
      setForm({
        name: "",
        metric: "cpu_percent",
        operator: "gte",
        threshold: 90,
        service_name: "",
        severity: "warning",
        cooldown_minutes: 30,
        notify_email: true,
        recipients: "",
      });
      setError(null);
      invalidate();
      setCreateOpen(false);
    },
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiRequest(`/monitoring/rules/${id}/`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const toggle = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      apiRequest(`/monitoring/rules/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active }),
      }),
    onSuccess: invalidate,
  });

  const evaluate = useMutation({
    mutationFn: () => apiRequest("/monitoring/evaluate/", { method: "POST", body: "{}" }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const ack = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/monitoring/events/${id}/acknowledge/`, { method: "POST", body: "{}" }),
    onSuccess: invalidate,
  });

  const resolve = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/monitoring/events/${id}/resolve/`, { method: "POST", body: "{}" }),
    onSuccess: invalidate,
  });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  const m = overview?.metrics;

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader title={title} subtitle="Seuils serveur, alertes ouvertes et notifications e-mail." stats={[{ label: "Règles actives", value: overview?.rules_active ?? "—" }, { label: "Alertes ouvertes", value: overview?.events_open ?? "—" }, { label: "CPU", value: m ? `${m.cpu_percent.toFixed(0)}%` : "—" }, { label: "RAM", value: m ? `${m.ram_percent.toFixed(0)}%` : "—" }, { label: "Disque", value: m ? `${m.disk_percent.toFixed(0)}%` : "—" }]} actions={<><IconAction label="Évaluer maintenant" onClick={() => evaluate.mutate()} disabled={evaluate.isPending}><RefreshCw className="h-4 w-4" /></IconAction><button type="button" className="vz-btn-primary" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> Ajouter un seuil</button></>} />

      {m?.services && (
        <div className="vz-panel flex flex-wrap gap-3 p-4 text-sm">
          {Object.entries(m.services).map(([name, active]) => (
            <StatusDot key={name} status={active ? "ok" : "error"} label={`${name} · ${active ? "opérationnel" : "indisponible"}`} />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          {error}
        </div>
      )}

      <div className="vz-panel overflow-hidden"><Tabs tabs={[{ id: "thresholds", label: "Seuils", count: rules.length }, { id: "alerts", label: "Alertes", count: events.filter((e) => e.status !== "resolved").length }]} active={tab} onChange={setTab} />
      {tab === "thresholds" && <div className="overflow-x-auto">
        <h2 className="md:col-span-4 text-sm font-semibold">Nouvelle règle</h2>
        <label className="text-sm md:col-span-2">
          Nom
          <input
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            required
          />
        </label>
        <label className="text-sm">
          Métrique
          <select
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={form.metric}
            onChange={(e) => setForm((f) => ({ ...f, metric: e.target.value }))}
          >
            <option value="cpu_percent">CPU %</option>
            <option value="ram_percent">RAM %</option>
            <option value="disk_percent">Disque %</option>
            <option value="load_1">Load 1m</option>
            <option value="service_down">Service down</option>
          </select>
        </label>
        <label className="text-sm">
          Opérateur
          <select
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={form.operator}
            onChange={(e) => setForm((f) => ({ ...f, operator: e.target.value }))}
          >
            <option value="gte">&gt;=</option>
            <option value="gt">&gt;</option>
            <option value="lte">&lt;=</option>
            <option value="lt">&lt;</option>
            <option value="eq">==</option>
          </select>
        </label>
        <label className="text-sm">
          Seuil
          <input
            type="number"
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={form.threshold}
            onChange={(e) => setForm((f) => ({ ...f, threshold: Number(e.target.value) }))}
          />
        </label>
        {form.metric === "service_down" && (
          <label className="text-sm">
            Service
            <input
              className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
              value={form.service_name}
              onChange={(e) => setForm((f) => ({ ...f, service_name: e.target.value }))}
              placeholder="redis, nginx…"
              required
            />
          </label>
        )}
        <label className="text-sm">
          Sévérité
          <select
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={form.severity}
            onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value }))}
          >
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
          </select>
        </label>
        <label className="text-sm">
          Cooldown (min)
          <input
            type="number"
            min={0}
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={form.cooldown_minutes}
            onChange={(e) => setForm((f) => ({ ...f, cooldown_minutes: Number(e.target.value) }))}
          />
        </label>
        <label className="text-sm md:col-span-2">
          Destinataires e-mail
          <input
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={form.recipients}
            onChange={(e) => setForm((f) => ({ ...f, recipients: e.target.value }))}
            placeholder="ops@example.com, noc@example.com"
          />
        </label>
        <label className="text-sm inline-flex items-center gap-2 pt-6">
          <input
            type="checkbox"
            checked={form.notify_email}
            onChange={(e) => setForm((f) => ({ ...f, notify_email: e.target.checked }))}
          />
          Notifier par e-mail
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            className="w-full rounded bg-cp-orange px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            disabled={create.isPending}
          >
            Ajouter
          </button>
        </div>
        <table className="min-w-full text-sm">
          <thead className="bg-cp-canvas text-left text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Règle</th>
              <th className="px-3 py-2">Condition</th>
              <th className="px-3 py-2">Sévérité</th>
              <th className="px-3 py-2">Actif</th>
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
                <td className="px-3 py-2 font-medium">{r.name}</td>
                <td className="px-3 py-2">
                  {r.metric === "service_down"
                    ? `service ${r.service_name} down`
                    : `${r.metric} ${r.operator} ${r.threshold}`}
                </td>
                <td className="px-3 py-2">{r.severity}</td>
                <td className="px-3 py-2">{r.is_active ? "oui" : "non"}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    <IconAction label={r.is_active ? `Désactiver ${r.name}` : `Activer ${r.name}`} onClick={() => toggle.mutate({ id: r.id, is_active: !r.is_active })}>{r.is_active ? <ToggleRight className="h-4 w-4" /> : <ToggleLeft className="h-4 w-4" />}</IconAction>
                    <IconAction label={`Supprimer ${r.name}`} danger onClick={() => remove.mutate(r.id)}><Trash2 className="h-4 w-4" /></IconAction>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>}
      {tab === "alerts" && <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-cp-canvas text-left text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Règle</th>
              <th className="px-3 py-2">Statut</th>
              <th className="px-3 py-2">Valeur</th>
              <th className="px-3 py-2">Message</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loadingEvents && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Chargement…
                </td>
              </tr>
            )}
            {!loadingEvents && events.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Aucun événement.
                </td>
              </tr>
            )}
            {events.map((ev) => (
              <tr key={ev.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2">
                  <div className="font-medium">{ev.rule_name}</div>
                  <div className="text-xs text-cp-muted">{ev.rule_severity}</div>
                </td>
                <td className="px-3 py-2">{ev.status}</td>
                <td className="px-3 py-2">{ev.metric_value ?? "—"}</td>
                <td className="px-3 py-2">{ev.message}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    {ev.status === "open" && (
                      <IconAction label={`Acquitter ${ev.rule_name}`} onClick={() => ack.mutate(ev.id)}><Check className="h-4 w-4" /></IconAction>
                    )}
                    {ev.status !== "resolved" && (
                      <IconAction label={`Résoudre ${ev.rule_name}`} onClick={() => resolve.mutate(ev.id)}><Check className="h-4 w-4" /></IconAction>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>}</div>
      {createOpen && <Modal title="Ajouter un seuil d’alerte" onClose={() => setCreateOpen(false)} wide><form onSubmit={onCreate} className="grid gap-3 sm:grid-cols-2"><input className="vz-input sm:col-span-2" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Nom de la règle" required /><select className="vz-input" value={form.metric} onChange={(e) => setForm((f) => ({ ...f, metric: e.target.value }))}><option value="cpu_percent">CPU %</option><option value="ram_percent">RAM %</option><option value="disk_percent">Disque %</option><option value="load_1">Charge 1m</option><option value="service_down">Service indisponible</option></select><select className="vz-input" value={form.operator} onChange={(e) => setForm((f) => ({ ...f, operator: e.target.value }))}><option value="gte">≥</option><option value="gt">&gt;</option><option value="lte">≤</option><option value="lt">&lt;</option><option value="eq">=</option></select><input className="vz-input" type="number" value={form.threshold} onChange={(e) => setForm((f) => ({ ...f, threshold: Number(e.target.value) }))} placeholder="Seuil" />{form.metric === "service_down" && <input className="vz-input" value={form.service_name} onChange={(e) => setForm((f) => ({ ...f, service_name: e.target.value }))} placeholder="Service (nginx…)" required />}<select className="vz-input" value={form.severity} onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value }))}><option value="info">Info</option><option value="warning">Avertissement</option><option value="critical">Critique</option></select><input className="vz-input" type="number" value={form.cooldown_minutes} onChange={(e) => setForm((f) => ({ ...f, cooldown_minutes: Number(e.target.value) }))} placeholder="Cooldown (min)" /><input className="vz-input sm:col-span-2" value={form.recipients} onChange={(e) => setForm((f) => ({ ...f, recipients: e.target.value }))} placeholder="Destinataires e-mail" /><label className="inline-flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={form.notify_email} onChange={(e) => setForm((f) => ({ ...f, notify_email: e.target.checked }))} /> Notifier par e-mail</label><div className="flex justify-end gap-2 sm:col-span-2"><button type="button" className="vz-btn-ghost" onClick={() => setCreateOpen(false)}>Annuler</button><button className="vz-btn-primary" disabled={create.isPending}>Ajouter</button></div></form></Modal>}
    </div>
  );
}
