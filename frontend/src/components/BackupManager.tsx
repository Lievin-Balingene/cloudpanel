import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Download, History, Plus, RotateCcw, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot, Tabs } from "@/components/ui/PageChrome";

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
  const [tab, setTab] = useState<"archives" | "schedules">("archives");
  const [createKind, setCreateKind] = useState<"backup" | "schedule" | null>(null);

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
      return runWithProgress(
        "Création sauvegarde",
        () =>
          apiRequest("/backups/archives/", {
            method: "POST",
            body: JSON.stringify({
              backup_type: form.backup_type,
              label: form.label,
              includes,
            }),
          }),
        {
          detail: form.label || form.backup_type,
          tickDetail: (ms) =>
            ms < 3000 ? "Préparation…" : ms < 10000 ? "Archivage des fichiers…" : "Compression…",
        },
      );
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
      setCreateKind(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const restore = useMutation({
    mutationFn: (id: number) =>
      runWithProgress(
        "Restauration sauvegarde",
        () => apiRequest(`/backups/archives/${id}/restore/`, { method: "POST", body: "{}" }),
        {
          tickDetail: (ms) =>
            ms < 4000 ? "Lecture de l'archive…" : "Restauration en cours…",
        },
      ),
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
      setCreateKind(null);
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
      <PageHeader
        title={title}
        subtitle={`Sauvegardes du compte, restauration et planification (${overview?.max_backups ?? "—"} archives maximum).`}
        stats={[
          { label: "Archives", value: overview?.archives ?? "—" },
          { label: "Terminées", value: overview?.completed ?? "—" },
          { label: "Restaurées", value: overview?.restored ?? "—" },
          { label: "Échouées", value: overview?.failed ?? "—" },
          { label: "Volume", value: overview ? formatBytes(overview.total_size_bytes) : "—" },
        ]}
        actions={<button type="button" className="vz-btn-primary" onClick={() => setCreateKind(tab === "schedules" ? "schedule" : "backup")}><Plus className="h-4 w-4" />{tab === "schedules" ? "Créer un planning" : "Créer une sauvegarde"}</button>}
      />

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

      <div className="vz-panel overflow-hidden">
        <Tabs tabs={[{ id: "archives", label: "Sauvegardes", count: overview?.archives ?? archives.length, icon: <History className="h-3.5 w-3.5" /> }, { id: "schedules", label: "Planifications", count: overview?.schedules ?? schedules.length, icon: <CalendarClock className="h-3.5 w-3.5" /> }]} active={tab} onChange={(id) => setTab(id as "archives" | "schedules")} />
        {tab === "archives" && <div className="overflow-x-auto">
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
                <td colSpan={5}><EmptyState icon={<History className="h-8 w-8" />} message="Aucune sauvegarde." action={<button type="button" className="vz-btn-primary" onClick={() => setCreateKind("backup")}><Plus className="h-4 w-4" />Créer une sauvegarde</button>} /></td>
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
                  <StatusDot status={a.status} />
                  {a.last_error && <div className="mt-1 text-xs text-red-600">{a.last_error}</div>}
                </td>
                <td className="px-3 py-2">{formatBytes(a.size_bytes)}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-0.5"><IconAction label="Restaurer" onClick={() => restore.mutate(a.id)}><RotateCcw className="h-4 w-4" /></IconAction><IconAction label="Afficher les informations de téléchargement" onClick={() => download.mutate(a.id)}><Download className="h-4 w-4" /></IconAction><IconAction label="Supprimer" danger onClick={() => remove.mutate(a.id)}><Trash2 className="h-4 w-4" /></IconAction></div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>}
        {tab === "schedules" && <div>{schedules.length === 0 ? <EmptyState icon={<CalendarClock className="h-8 w-8" />} message="Aucune planification automatique." action={<button type="button" className="vz-btn-primary" onClick={() => setCreateKind("schedule")}><Plus className="h-4 w-4" />Créer un planning</button>} /> : <div className="divide-y divide-cp-border dark:divide-ink-800">{schedules.map((schedule) => <div key={schedule.id} className="flex items-center justify-between gap-3 px-4 py-3"><div><p className="font-medium">{schedule.frequency} à {schedule.hour} h</p><div className="mt-1 flex items-center gap-2 text-xs text-cp-muted"><StatusDot status={schedule.is_active ? "active" : "inactive"} /><span>{schedule.last_run_at ? `Dernière exécution : ${new Date(schedule.last_run_at).toLocaleString("fr-FR")}` : "Jamais exécutée"}</span></div></div><IconAction label="Supprimer la planification" danger onClick={() => deleteSchedule.mutate(schedule.id)}><Trash2 className="h-4 w-4" /></IconAction></div>)}</div>}</div>}
      </div>
      {createKind === "backup" && <Modal title="Nouvelle sauvegarde" onClose={() => setCreateKind(null)}><form className="space-y-3" onSubmit={onCreate}><div><label className="mb-1 block text-xs font-medium text-cp-muted">Type</label><select className="vz-input" value={form.backup_type} onChange={(e) => setForm((f) => ({ ...f, backup_type: e.target.value }))}><option value="full">Complète</option><option value="home">Fichiers</option><option value="databases">Bases</option><option value="email">Email</option><option value="custom">Personnalisée</option></select></div><div><label className="mb-1 block text-xs font-medium text-cp-muted">Libellé</label><input className="vz-input" value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))} placeholder="Optionnel" /></div>{form.backup_type === "custom" && <div className="flex flex-wrap gap-4 text-sm">{[["includes_home", "Fichiers (home)"], ["includes_databases", "Bases"], ["includes_email", "Email"]].map(([key, label]) => <label key={key} className="inline-flex items-center gap-2"><input type="checkbox" checked={Boolean(form[key as keyof typeof form])} onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.checked }))} />{label}</label>)}</div>}<div className="flex justify-end gap-2"><button type="button" className="vz-btn-ghost" onClick={() => setCreateKind(null)}>Annuler</button><button className="vz-btn-primary" type="submit" disabled={create.isPending}>{create.isPending ? "Création…" : "Créer"}</button></div></form></Modal>}
      {createKind === "schedule" && <Modal title="Nouvelle planification" onClose={() => setCreateKind(null)}><form className="space-y-3" onSubmit={onSchedule}><div><label className="mb-1 block text-xs font-medium text-cp-muted">Fréquence</label><select className="vz-input" value={scheduleForm.frequency} onChange={(e) => setScheduleForm((f) => ({ ...f, frequency: e.target.value }))}><option value="daily">Quotidien</option><option value="weekly">Hebdomadaire</option><option value="monthly">Mensuel</option></select></div><div className="grid grid-cols-2 gap-3"><div><label className="mb-1 block text-xs font-medium text-cp-muted">Heure</label><input className="vz-input" type="number" min={0} max={23} value={scheduleForm.hour} onChange={(e) => setScheduleForm((f) => ({ ...f, hour: Number(e.target.value) }))} /></div><div><label className="mb-1 block text-xs font-medium text-cp-muted">Jour (0 = lundi)</label><input className="vz-input" type="number" min={0} max={6} value={scheduleForm.weekday} onChange={(e) => setScheduleForm((f) => ({ ...f, weekday: Number(e.target.value) }))} /></div></div><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={scheduleForm.is_active} onChange={(e) => setScheduleForm((f) => ({ ...f, is_active: e.target.checked }))} />Actif</label><div className="flex justify-end gap-2"><button type="button" className="vz-btn-ghost" onClick={() => setCreateKind(null)}>Annuler</button><button className="vz-btn-primary" type="submit" disabled={saveSchedule.isPending}>{saveSchedule.isPending ? "Enregistrement…" : "Créer"}</button></div></form></Modal>}
    </div>
  );
}
