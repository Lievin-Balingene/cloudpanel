import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Bell,
  Check,
  Cpu,
  HardDrive,
  MemoryStick,
  Plus,
  RefreshCw,
  Server,
  ToggleLeft,
  ToggleRight,
  Trash2,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot, Tabs } from "@/components/ui/PageChrome";

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

const METRIC_LABELS: Record<string, string> = {
  cpu_percent: "CPU",
  ram_percent: "RAM",
  disk_percent: "Disque",
  load_1: "Charge 1 min",
  service_down: "Service",
};

const OP_LABELS: Record<string, string> = {
  gte: "≥",
  gt: ">",
  lte: "≤",
  lt: "<",
  eq: "=",
};

const SEVERITY_STYLES: Record<string, string> = {
  info: "bg-sky-50 text-sky-700 ring-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:ring-sky-900",
  warning:
    "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-900",
  critical:
    "bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-900",
};

const STATUS_LABELS: Record<string, string> = {
  open: "Ouverte",
  acknowledged: "Acquittée",
  resolved: "Résolue",
};

function tone(percent: number | undefined): "ok" | "warn" | "bad" | "idle" {
  if (percent == null || Number.isNaN(percent)) return "idle";
  if (percent >= 90) return "bad";
  if (percent >= 70) return "warn";
  return "ok";
}

const toneBar: Record<string, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-400",
  bad: "bg-rose-500",
  idle: "bg-slate-300",
};

function MetricCard({
  icon: Icon,
  label,
  percent,
  hint,
}: {
  icon: typeof Cpu;
  label: string;
  percent?: number;
  hint?: string;
}) {
  const t = tone(percent);
  const pct = typeof percent === "number" ? Math.min(100, Math.max(0, percent)) : 0;
  return (
    <div className="rounded-xl border border-cp-border/70 bg-white p-3.5 dark:border-ink-700 dark:bg-ink-950">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium text-cp-text">
          <Icon className="h-4 w-4 text-cp-muted" />
          {label}
        </div>
        <span className="text-sm font-semibold tabular-nums text-cp-text">
          {typeof percent === "number" ? `${percent.toFixed(0)}%` : "—"}
        </span>
      </div>
      <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-cp-canvas dark:bg-ink-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${toneBar[t]}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {hint ? <p className="mt-1.5 text-[11px] text-cp-muted">{hint}</p> : null}
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const key = severity in SEVERITY_STYLES ? severity : "info";
  const label =
    severity === "critical" ? "Critique" : severity === "warning" ? "Avertissement" : "Info";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${SEVERITY_STYLES[key]}`}
    >
      {label}
    </span>
  );
}

function formatCondition(r: AlertRuleItem) {
  if (r.metric === "service_down") return `Service « ${r.service_name || "?"} » indisponible`;
  return `${METRIC_LABELS[r.metric] || r.metric} ${OP_LABELS[r.operator] || r.operator} ${r.threshold}`;
}

function formatWhen(iso: string | null) {
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

const emptyForm = {
  name: "",
  metric: "cpu_percent",
  operator: "gte",
  threshold: 90,
  service_name: "",
  severity: "warning",
  cooldown_minutes: 30,
  notify_email: true,
  recipients: "",
};

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

  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("thresholds");
  const [createOpen, setCreateOpen] = useState(false);

  const openEvents = useMemo(
    () => events.filter((e) => e.status !== "resolved"),
    [events],
  );

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
      setForm(emptyForm);
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
  const services = m?.services ? Object.entries(m.services) : [];
  const downCount = services.filter(([, ok]) => !ok).length;

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Surveillez CPU, RAM, disque et services. Recevez une alerte e-mail si un seuil est dépassé."
        stats={[
          { label: "Seuils actifs", value: overview?.rules_active ?? "—" },
          { label: "Alertes ouvertes", value: overview?.events_open ?? "—" },
          {
            label: "Services",
            value: services.length ? `${services.length - downCount}/${services.length}` : "—",
          },
        ]}
        actions={
          <>
            <button
              type="button"
              className="vz-btn-ghost"
              onClick={() => evaluate.mutate()}
              disabled={evaluate.isPending}
            >
              <RefreshCw className={`h-4 w-4 ${evaluate.isPending ? "animate-spin" : ""}`} />
              Vérifier maintenant
            </button>
            <button type="button" className="vz-btn-primary" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" />
              Ajouter un seuil
            </button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Cpu} label="CPU" percent={m?.cpu_percent} />
        <MetricCard icon={MemoryStick} label="Mémoire" percent={m?.ram_percent} />
        <MetricCard icon={HardDrive} label="Disque" percent={m?.disk_percent} />
        <MetricCard
          icon={Activity}
          label="Charge"
          percent={
            typeof m?.load_1 === "number" ? Math.min(100, Math.round(m.load_1 * 25)) : undefined
          }
          hint={typeof m?.load_1 === "number" ? `Load 1 min · ${m.load_1.toFixed(2)}` : undefined}
        />
      </div>

      {services.length > 0 && (
        <div className="vz-panel p-3.5 sm:p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-cp-text">
            <Server className="h-4 w-4 text-cp-muted" />
            État des services
            {downCount > 0 ? (
              <span className="rounded-md bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-700 ring-1 ring-inset ring-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-900">
                {downCount} indisponible{downCount > 1 ? "s" : ""}
              </span>
            ) : (
              <span className="rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900">
                Tout opérationnel
              </span>
            )}
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {services.map(([name, active]) => (
              <div
                key={name}
                className="flex items-center justify-between gap-2 rounded-lg border border-cp-border/60 bg-cp-canvas/50 px-3 py-2 dark:border-ink-700 dark:bg-ink-900/50"
              >
                <span className="truncate text-sm font-medium text-cp-text">{name}</span>
                <StatusDot
                  status={active ? "ok" : "error"}
                  label={active ? "OK" : "Down"}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200">
          {error}
        </div>
      )}

      <div className="vz-panel overflow-hidden">
        <Tabs
          tabs={[
            { id: "thresholds", label: "Seuils", count: rules.length, icon: <Bell className="h-3.5 w-3.5" /> },
            {
              id: "alerts",
              label: "Alertes",
              count: openEvents.length,
              icon: <AlertTriangle className="h-3.5 w-3.5" />,
            },
          ]}
          active={tab}
          onChange={setTab}
        />

        {tab === "thresholds" && (
          <div>
            {loadingRules ? (
              <p className="px-4 py-10 text-center text-sm text-cp-muted">Chargement…</p>
            ) : rules.length === 0 ? (
              <EmptyState
                icon={<Bell className="h-5 w-5" />}
                message="Aucun seuil configuré. Ajoutez une règle pour être alerté en cas de problème."
                action={
                  <button type="button" className="vz-btn-primary" onClick={() => setCreateOpen(true)}>
                    <Plus className="h-4 w-4" />
                    Ajouter un seuil
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
                        <SeverityBadge severity={r.severity} />
                        <StatusDot
                          status={r.is_active ? "active" : "inactive"}
                          label={r.is_active ? "Actif" : "Pause"}
                        />
                      </div>
                      <p className="text-sm text-cp-muted">{formatCondition(r)}</p>
                      <p className="text-[11px] text-cp-muted">
                        Cooldown {r.cooldown_minutes} min
                        {r.notify_email ? " · E-mail activé" : " · Sans e-mail"}
                        {r.last_triggered_at
                          ? ` · Dernier déclenchement ${formatWhen(r.last_triggered_at)}`
                          : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <IconAction
                        label={r.is_active ? `Désactiver ${r.name}` : `Activer ${r.name}`}
                        onClick={() => toggle.mutate({ id: r.id, is_active: !r.is_active })}
                      >
                        {r.is_active ? (
                          <ToggleRight className="h-4 w-4" />
                        ) : (
                          <ToggleLeft className="h-4 w-4" />
                        )}
                      </IconAction>
                      <IconAction
                        label={`Supprimer ${r.name}`}
                        danger
                        onClick={() => {
                          if (window.confirm(`Supprimer le seuil « ${r.name} » ?`)) {
                            remove.mutate(r.id);
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

        {tab === "alerts" && (
          <div>
            {loadingEvents ? (
              <p className="px-4 py-10 text-center text-sm text-cp-muted">Chargement…</p>
            ) : events.length === 0 ? (
              <EmptyState
                icon={<Check className="h-5 w-5" />}
                message="Aucune alerte pour le moment. Tout semble calme."
              />
            ) : (
              <ul className="divide-y divide-cp-border dark:divide-ink-800">
                {events.map((ev) => (
                  <li
                    key={ev.id}
                    className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold text-cp-text">{ev.rule_name}</p>
                        <SeverityBadge severity={ev.rule_severity} />
                        <StatusDot
                          status={
                            ev.status === "resolved"
                              ? "ok"
                              : ev.status === "open"
                                ? "error"
                                : "inactive"
                          }
                          label={STATUS_LABELS[ev.status] || ev.status}
                        />
                      </div>
                      <p className="text-sm text-cp-muted">{ev.message || "—"}</p>
                      <p className="text-[11px] text-cp-muted">
                        {formatWhen(ev.created_at)}
                        {ev.metric_value != null ? ` · Valeur ${ev.metric_value}` : ""}
                        {ev.notified ? " · Notifié" : ""}
                      </p>
                    </div>
                    {ev.status !== "resolved" && (
                      <div className="flex shrink-0 flex-wrap gap-2">
                        {ev.status === "open" && (
                          <button
                            type="button"
                            className="vz-btn-ghost !py-1.5 text-xs"
                            onClick={() => ack.mutate(ev.id)}
                          >
                            Acquitter
                          </button>
                        )}
                        <button
                          type="button"
                          className="vz-btn-primary !py-1.5 text-xs"
                          onClick={() => resolve.mutate(ev.id)}
                        >
                          Résoudre
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {createOpen && (
        <Modal title="Ajouter un seuil d’alerte" onClose={() => setCreateOpen(false)} wide>
          <form onSubmit={onCreate} className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm sm:col-span-2">
              <span className="mb-1 block font-medium text-cp-text">Nom</span>
              <input
                className="vz-input w-full"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Ex. CPU élevé"
                required
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-cp-text">Métrique</span>
              <select
                className="vz-input w-full"
                value={form.metric}
                onChange={(e) => setForm((f) => ({ ...f, metric: e.target.value }))}
              >
                <option value="cpu_percent">CPU %</option>
                <option value="ram_percent">RAM %</option>
                <option value="disk_percent">Disque %</option>
                <option value="load_1">Charge 1 min</option>
                <option value="service_down">Service indisponible</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-cp-text">Condition</span>
              <select
                className="vz-input w-full"
                value={form.operator}
                onChange={(e) => setForm((f) => ({ ...f, operator: e.target.value }))}
              >
                <option value="gte">≥</option>
                <option value="gt">&gt;</option>
                <option value="lte">≤</option>
                <option value="lt">&lt;</option>
                <option value="eq">=</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-cp-text">Seuil</span>
              <input
                className="vz-input w-full"
                type="number"
                value={form.threshold}
                onChange={(e) => setForm((f) => ({ ...f, threshold: Number(e.target.value) }))}
              />
            </label>
            {form.metric === "service_down" && (
              <label className="block text-sm">
                <span className="mb-1 block font-medium text-cp-text">Nom du service</span>
                <input
                  className="vz-input w-full"
                  value={form.service_name}
                  onChange={(e) => setForm((f) => ({ ...f, service_name: e.target.value }))}
                  placeholder="nginx, redis…"
                  required
                />
              </label>
            )}
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-cp-text">Sévérité</span>
              <select
                className="vz-input w-full"
                value={form.severity}
                onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value }))}
              >
                <option value="info">Info</option>
                <option value="warning">Avertissement</option>
                <option value="critical">Critique</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-cp-text">Cooldown (minutes)</span>
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                value={form.cooldown_minutes}
                onChange={(e) =>
                  setForm((f) => ({ ...f, cooldown_minutes: Number(e.target.value) }))
                }
              />
            </label>
            <label className="block text-sm sm:col-span-2">
              <span className="mb-1 block font-medium text-cp-text">Destinataires e-mail</span>
              <input
                className="vz-input w-full"
                value={form.recipients}
                onChange={(e) => setForm((f) => ({ ...f, recipients: e.target.value }))}
                placeholder="ops@exemple.com"
              />
            </label>
            <label className="inline-flex items-center gap-2 text-sm sm:col-span-2">
              <input
                type="checkbox"
                className="accent-cp-orange"
                checked={form.notify_email}
                onChange={(e) => setForm((f) => ({ ...f, notify_email: e.target.checked }))}
              />
              Envoyer une notification e-mail
            </label>
            <div className="flex justify-end gap-2 sm:col-span-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setCreateOpen(false)}>
                Annuler
              </button>
              <button className="vz-btn-primary" disabled={create.isPending}>
                {create.isPending ? "Ajout…" : "Ajouter"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
