import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, FileText, PauseCircle, PlayCircle, Plus, RefreshCw, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { EmptyState, PageHeader } from "@/components/ui/PageChrome";

interface CronJob {
  id: number;
  owner_username: string;
  common: string;
  minute: string;
  hour: string;
  day: string;
  month: string;
  weekday: string;
  schedule_line: string;
  command: string;
  email_to: string;
  label: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface CronOverview {
  jobs: number;
  active: number;
  inactive: number;
  quota_limit: number;
  quota_used: number;
  home_path: string;
  common_presets: { value: string; label: string }[];
}

const EMPTY_FORM = {
  common: "once_per_day",
  minute: "0",
  hour: "0",
  day: "*",
  month: "*",
  weekday: "*",
  command: "",
  email_to: "",
  label: "",
};

export function CronManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<CronJob | null>(null);

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["cron-jobs"],
    queryFn: () => apiRequest<CronJob[]>("/cron/jobs/"),
  });

  const { data: overview } = useQuery({
    queryKey: ["cron-overview"],
    queryFn: () => apiRequest<CronOverview>("/cron/overview/"),
  });

  const { data: preview, refetch: refetchPreview } = useQuery({
    queryKey: ["cron-preview"],
    queryFn: () => apiRequest<{ crontab: string; filename: string }>("/cron/preview/"),
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["cron-jobs"] });
    void qc.invalidateQueries({ queryKey: ["cron-overview"] });
    void qc.invalidateQueries({ queryKey: ["cron-preview"] });
  };

  const createMut = useMutation({
    mutationFn: () =>
      apiRequest("/cron/jobs/", {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const updateMut = useMutation({
    mutationFn: (payload: { id: number; data: Record<string, unknown> }) =>
      apiRequest(`/cron/jobs/${payload.id}/`, {
        method: "PATCH",
        body: JSON.stringify(payload.data),
      }),
    onSuccess: () => {
      setEditing(null);
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiRequest(`/cron/jobs/${id}/`, { method: "DELETE" }),
    onSuccess: () => invalidate(),
    onError: (err: Error) => setError(err.message),
  });

  const syncMut = useMutation({
    mutationFn: () => apiRequest("/cron/sync/", { method: "POST", body: "{}" }),
    onSuccess: () => {
      void refetchPreview();
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const presets = overview?.common_presets ?? [];
  const isCustom = form.common === "custom";
  const quotaLabel = useMemo(() => {
    if (!overview) return "";
    if (!overview.quota_limit) return `${overview.quota_used} / ∞`;
    return `${overview.quota_used} / ${overview.quota_limit}`;
  }, [overview]);

  function onCreate(e: FormEvent) {
    e.preventDefault();
    createMut.mutate();
  }

  function startEdit(job: CronJob) {
    setEditing(job);
    setForm({
      common: job.common,
      minute: job.minute,
      hour: job.hour,
      day: job.day,
      month: job.month,
      weekday: job.weekday,
      command: job.command,
      email_to: job.email_to,
      label: job.label,
    });
  }

  function onSaveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    updateMut.mutate({ id: editing.id, data: form });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={title}
        subtitle="Planifiez des commandes comme sur cPanel (Common Settings + Standard)."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Tâches", value: overview?.jobs ?? "—" },
          { label: "Actives", value: overview?.active ?? "—" },
          { label: "Inactives", value: overview?.inactive ?? "—" },
          { label: "Quota", value: quotaLabel || "—" },
        ].map((c) => (
          <div key={c.label} className="vz-panel px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">{c.label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-cp-navy dark:text-ink-50">
              {c.value}
            </p>
          </div>
        ))}
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
          {error}
        </p>
      )}

      <form className="vz-panel space-y-4 p-4 sm:p-5" onSubmit={editing ? onSaveEdit : onCreate}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-cp-navy dark:text-ink-50">
            <Plus className="h-4 w-4 text-cp-orange" />
            {editing ? `Modifier #${editing.id}` : "Add New Cron Job"}
          </h2>
          {editing && (
            <button
              type="button"
              className="vz-btn-ghost vz-btn-sm"
              onClick={() => {
                setEditing(null);
                setForm(EMPTY_FORM);
              }}
            >
              Annuler
            </button>
          )}
        </div>

        <label className="block space-y-1 text-sm">
          <span className="text-xs font-medium text-cp-muted">Common Settings</span>
          <select
            className="vz-input"
            value={form.common}
            onChange={(e) => setForm({ ...form, common: e.target.value })}
          >
            {(presets.length
              ? presets
              : [
                  { value: "custom", label: "Custom" },
                  { value: "once_per_minute", label: "Once Per Minute" },
                  { value: "once_per_five", label: "Once Per Five Minutes" },
                  { value: "once_per_hour", label: "Once Per Hour" },
                  { value: "once_per_day", label: "Once Per Day" },
                  { value: "once_per_week", label: "Once Per Week" },
                  { value: "once_per_month", label: "Once Per Month" },
                ]
            ).map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>

        {isCustom && (
          <div className="grid gap-2 sm:grid-cols-5">
            {(
              [
                ["minute", "Minute"],
                ["hour", "Hour"],
                ["day", "Day"],
                ["month", "Month"],
                ["weekday", "Weekday"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="block space-y-1 text-sm">
                <span className="text-xs font-medium text-cp-muted">{label}</span>
                <input
                  className="vz-input font-mono"
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  required
                />
              </label>
            ))}
          </div>
        )}

        <label className="block space-y-1 text-sm">
          <span className="text-xs font-medium text-cp-muted">Command</span>
          <input
            className="vz-input font-mono"
            placeholder="/usr/bin/php -q public_html/cron.php"
            value={form.command}
            onChange={(e) => setForm({ ...form, command: e.target.value })}
            required
          />
          <span className="text-[11px] text-cp-muted">
            Exécutée depuis le home ({overview?.home_path || "~/"}).
          </span>
        </label>

        <div className="grid gap-2 sm:grid-cols-2">
          <label className="block space-y-1 text-sm">
            <span className="text-xs font-medium text-cp-muted">Label (optionnel)</span>
            <input
              className="vz-input"
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-xs font-medium text-cp-muted">Email (sortie cron)</span>
            <input
              className="vz-input"
              type="email"
              placeholder="vous@exemple.com"
              value={form.email_to}
              onChange={(e) => setForm({ ...form, email_to: e.target.value })}
            />
          </label>
        </div>

        <button type="submit" className="vz-btn-primary" disabled={createMut.isPending || updateMut.isPending}>
          {editing ? "Enregistrer" : "Add New Cron Job"}
        </button>
      </form>

      <div className="vz-panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cp-border px-4 py-3 dark:border-ink-800">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Clock className="h-4 w-4 text-cp-orange" />
            Current Cron Jobs
          </h2>
          <button
            type="button"
            className="vz-btn-ghost vz-btn-sm"
            onClick={() => syncMut.mutate()}
            disabled={syncMut.isPending}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncMut.isPending ? "animate-spin" : ""}`} />
            Sync crontab
          </button>
        </div>

        {isLoading ? (
          <p className="p-4 text-sm text-cp-muted">Chargement…</p>
        ) : !jobs.length ? (
          <EmptyState icon={<Clock className="h-8 w-8" />} message="Aucune tâche cron — ajoutez-en une ci-dessus." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-cp-canvas text-[11px] uppercase tracking-wide text-cp-muted dark:bg-ink-900">
                <tr>
                  <th className="px-3 py-2">Schedule</th>
                  <th className="px-3 py-2">Command</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id} className="border-t border-cp-border/70 dark:border-ink-800">
                    <td className="px-3 py-2 align-top">
                      <code className="font-mono text-xs">{job.schedule_line}</code>
                      {job.label && <p className="mt-0.5 text-xs text-cp-muted">{job.label}</p>}
                    </td>
                    <td className="max-w-md truncate px-3 py-2 align-top font-mono text-xs" title={job.command}>
                      {job.command}
                    </td>
                    <td className="px-3 py-2 align-top text-xs">
                      {job.is_active ? (
                        <span className="text-emerald-700 dark:text-emerald-400">Active</span>
                      ) : (
                        <span className="text-cp-muted">Inactive</span>
                      )}
                    </td>
                    <td className="px-3 py-2 align-top">
                      <div className="flex justify-end gap-1">
                        <IconAction title="Edit" onClick={() => startEdit(job)}>
                          <FileText className="h-3.5 w-3.5" />
                        </IconAction>
                        <IconAction
                          title={job.is_active ? "Disable" : "Enable"}
                          onClick={() =>
                            updateMut.mutate({
                              id: job.id,
                              data: { is_active: !job.is_active },
                            })
                          }
                        >
                          {job.is_active ? (
                            <PauseCircle className="h-3.5 w-3.5" />
                          ) : (
                            <PlayCircle className="h-3.5 w-3.5" />
                          )}
                        </IconAction>
                        <IconAction
                          title="Delete"
                          danger
                          onClick={() => {
                            if (window.confirm("Supprimer cette tâche cron ?")) {
                              deleteMut.mutate(job.id);
                            }
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </IconAction>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {preview?.crontab && (
        <div className="vz-panel p-4">
          <h2 className="mb-2 text-sm font-semibold">
            Crontab installé — <code className="font-mono text-xs">/etc/cron.d/{preview.filename}</code>
          </h2>
          <pre className="max-h-64 overflow-auto rounded-md bg-[#0f172a] px-3 py-2.5 font-mono text-[11px] leading-relaxed text-slate-200 whitespace-pre-wrap">
            {preview.crontab}
          </pre>
        </div>
      )}
    </div>
  );
}
