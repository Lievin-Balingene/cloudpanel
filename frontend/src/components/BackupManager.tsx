import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

interface BackupOverview {
  archives: number;
  completed: number;
  failed: number;
  restored: number;
  total_size_bytes: number;
  schedules: number;
  max_backups: number;
  provision_mode: string;
}

interface BackupArchiveItem {
  id: number;
  name: string;
  label: string;
  backup_type: string;
  includes: string[];
  status: string;
  size_bytes: number;
  checksum: string;
  last_error: string;
  completed_at: string | null;
  restored_at: string | null;
}

interface BackupScheduleItem {
  id: number;
  frequency: string;
  includes: string[];
  hour: number;
  weekday: number;
  is_active: boolean;
  last_run_at: string | null;
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} o`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} Ko`;
  return `${(n / (1024 * 1024)).toFixed(1)} Mo`;
}

export function BackupManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["backup-overview"],
    queryFn: () => apiRequest<BackupOverview>("/backups/overview/"),
  });
  const { data: archives = [], isLoading } = useQuery({
    queryKey: ["backup-archives"],
    queryFn: () => apiRequest<BackupArchiveItem[]>("/backups/archives/"),
  });
  const { data: schedules = [] } = useQuery({
    queryKey: ["backup-schedules"],
    queryFn: () => apiRequest<BackupScheduleItem[]>("/backups/schedules/"),
  });

  const [form, setForm] = useState({
    backup_type: "full",
    label: "",
    includes_home: true,
    includes_databases: true,
    includes_email: true,
  });
  const [scheduleForm, setScheduleForm] = useState({
    frequency: "weekly",
    hour: 2,
    weekday: 0,
    is_active: true,
  });
  const [downloadInfo, setDownloadInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["backup-overview"] });
    void qc.invalidateQueries({ queryKey: ["backup-archives"] });
    void qc.invalidateQueries({ queryKey: ["backup-schedules"] });
  };

  const create = useMutation({
    mutationFn: () => {
      const includes =
        form.backup_type === "custom"
          ? [
              form.includes_home ? "home" : null,
              form.includes_databases ? "databases" : null,
              form.includes_email ? "email" : null,
            ].filter(Boolean)
          : [];
      return apiRequest("/backups/archives/", {
        method: "POST",
        body: JSON.stringify({
          backup_type: form.backup_type,
          label: form.label,
          includes,
        }),
      });
    },
    onSuccess: () => {
      setForm({
        backup_type: "full",
        label: "",
        includes_home: true,
        includes_databases: true,
        includes_email: true,
      });
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const restore = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/backups/archives/${id}/restore/`, { method: "POST", body: "{}" }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiRequest(`/backups/archives/${id}/`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  });

  const download = useMutation({
    mutationFn: (id: number) =>
      apiRequest<{ file_name: string; size_bytes: number; checksum: string; path: string }>(
        `/backups/archives/${id}/download/`,
      ),
    onSuccess: (data) =>
      setDownloadInfo(`${data.file_name} — ${formatBytes(data.size_bytes)} — sha256:${data.checksum.slice(0, 12)}…`),
    onError: (err: Error) => setError(err.message),
  });

  const saveSchedule = useMutation({
    mutationFn: () =>
      apiRequest("/backups/schedules/", {
        method: "POST",
        body: JSON.stringify({
          frequency: scheduleForm.frequency,
          hour: scheduleForm.hour,
          weekday: scheduleForm.weekday,
          is_active: scheduleForm.is_active,
          includes: ["home", "databases", "email"],
        }),
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const deleteSchedule = useMutation({
    mutationFn: (id: number) => apiRequest(`/backups/schedules/${id}/`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  function onSchedule(e: FormEvent) {
    e.preventDefault();
    saveSchedule.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-cp-muted">
          Sauvegardes compte — création, restauration, planning et quotas ({overview?.max_backups ?? "—"} max).
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[
          { label: "Archives", value: overview?.archives ?? "—" },
          { label: "Terminées", value: overview?.completed ?? "—" },
          { label: "Restaurées", value: overview?.restored ?? "—" },
          { label: "Échouées", value: overview?.failed ?? "—" },
          { label: "Volume", value: overview ? formatBytes(overview.total_size_bytes) : "—" },
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
      {downloadInfo && (
        <div className="rounded border border-cp-border bg-cp-canvas px-3 py-2 text-sm dark:border-ink-800 dark:bg-ink-900">
          Téléchargement : {downloadInfo}
        </div>
      )}

      <form onSubmit={onCreate} className="vz-panel grid gap-3 p-4 md:grid-cols-4">
        <label className="text-sm">
          Type
          <select
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={form.backup_type}
            onChange={(e) => setForm((f) => ({ ...f, backup_type: e.target.value }))}
          >
            <option value="full">Complète</option>
            <option value="home">Fichiers</option>
            <option value="databases">Bases</option>
            <option value="email">Email</option>
            <option value="custom">Personnalisée</option>
          </select>
        </label>
        <label className="text-sm md:col-span-2">
          Libellé
          <input
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={form.label}
            onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
            placeholder="optionnel"
          />
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            className="w-full rounded bg-cp-orange px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            disabled={create.isPending}
          >
            {create.isPending ? "Création…" : "Créer une sauvegarde"}
          </button>
        </div>
        {form.backup_type === "custom" && (
          <div className="md:col-span-4 flex flex-wrap gap-4 text-sm">
            {[
              ["includes_home", "Fichiers (home)"],
              ["includes_databases", "Bases"],
              ["includes_email", "Email"],
            ].map(([key, label]) => (
              <label key={key} className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={Boolean(form[key as keyof typeof form])}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.checked }))}
                />
                {label}
              </label>
            ))}
          </div>
        )}
      </form>

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-cp-canvas text-left text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Nom</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Statut</th>
              <th className="px-3 py-2">Taille</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Chargement…
                </td>
              </tr>
            )}
            {!isLoading && archives.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Aucune sauvegarde.
                </td>
              </tr>
            )}
            {archives.map((a) => (
              <tr key={a.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2">
                  <div className="font-medium">{a.label || a.name}</div>
                  <div className="text-xs text-cp-muted">{a.includes?.join(", ")}</div>
                </td>
                <td className="px-3 py-2">{a.backup_type}</td>
                <td className="px-3 py-2">
                  <span className="rounded bg-cp-orange-soft px-2 py-0.5 text-xs dark:bg-ink-800">{a.status}</span>
                  {a.last_error && <div className="mt-1 text-xs text-red-600">{a.last_error}</div>}
                </td>
                <td className="px-3 py-2">{formatBytes(a.size_bytes)}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="text-xs text-cp-orange hover:underline"
                      onClick={() => restore.mutate(a.id)}
                    >
                      Restaurer
                    </button>
                    <button
                      type="button"
                      className="text-xs text-cp-orange hover:underline"
                      onClick={() => download.mutate(a.id)}
                    >
                      Infos DL
                    </button>
                    <button
                      type="button"
                      className="text-xs text-red-600 hover:underline"
                      onClick={() => remove.mutate(a.id)}
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

      <form onSubmit={onSchedule} className="vz-panel grid gap-3 p-4 md:grid-cols-5">
        <h2 className="md:col-span-5 text-sm font-semibold">Planning automatique</h2>
        <label className="text-sm">
          Fréquence
          <select
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={scheduleForm.frequency}
            onChange={(e) => setScheduleForm((f) => ({ ...f, frequency: e.target.value }))}
          >
            <option value="daily">Quotidien</option>
            <option value="weekly">Hebdomadaire</option>
            <option value="monthly">Mensuel</option>
          </select>
        </label>
        <label className="text-sm">
          Heure
          <input
            type="number"
            min={0}
            max={23}
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={scheduleForm.hour}
            onChange={(e) => setScheduleForm((f) => ({ ...f, hour: Number(e.target.value) }))}
          />
        </label>
        <label className="text-sm">
          Jour (0=lun)
          <input
            type="number"
            min={0}
            max={6}
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={scheduleForm.weekday}
            onChange={(e) => setScheduleForm((f) => ({ ...f, weekday: Number(e.target.value) }))}
          />
        </label>
        <label className="text-sm inline-flex items-center gap-2 pt-6">
          <input
            type="checkbox"
            checked={scheduleForm.is_active}
            onChange={(e) => setScheduleForm((f) => ({ ...f, is_active: e.target.checked }))}
          />
          Actif
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            className="w-full rounded border border-cp-border px-3 py-2 text-sm font-medium dark:border-ink-700"
            disabled={saveSchedule.isPending}
          >
            Enregistrer
          </button>
        </div>
        {schedules.length > 0 && (
          <div className="md:col-span-5 text-sm text-cp-muted">
            {schedules.map((s) => (
              <div key={s.id} className="flex items-center justify-between border-t border-cp-border py-2 dark:border-ink-800">
                <span>
                  {s.frequency} @ {s.hour}h — {s.is_active ? "actif" : "inactif"}
                  {s.last_run_at ? ` — dernier: ${new Date(s.last_run_at).toLocaleString()}` : ""}
                </span>
                <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => deleteSchedule.mutate(s.id)}>
                  Supprimer
                </button>
              </div>
            ))}
          </div>
        )}
      </form>
    </div>
  );
}
