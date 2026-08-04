import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, FolderKey, PauseCircle, PlayCircle, Plus, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot, Tabs } from "@/components/ui/PageChrome";

interface FtpAccount {
  id: number;
  username: string;
  owner_username: string;
  relative_directory: string;
  directory: string;
  quota_mb: number;
  bandwidth_kbs: number;
  is_active: boolean;
  is_suspended: boolean;
  can_write: boolean;
  status: string;
  last_login_at: string | null;
  last_login_ip: string | null;
  notes: string;
}

interface FtpLog {
  id: number;
  event_type: string;
  username: string;
  path: string;
  bytes_transferred: number;
  ip_address: string | null;
  message: string;
  success: boolean;
  created_at: string;
}

interface FtpStats {
  accounts_total: number;
  accounts_active: number;
  accounts_suspended: number;
  failed_logins_24h: number;
}

export function FtpManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ["ftp-accounts"],
    queryFn: () => apiRequest<FtpAccount[]>("/ftp/accounts/"),
  });
  const { data: logs = [] } = useQuery({
    queryKey: ["ftp-logs"],
    queryFn: () => apiRequest<FtpLog[]>("/ftp/logs/?limit=50"),
  });
  const { data: stats } = useQuery({
    queryKey: ["ftp-stats"],
    queryFn: () => apiRequest<FtpStats>("/ftp/stats/"),
  });

  const [form, setForm] = useState({
    username: "",
    password: "",
    relative_directory: "public_html",
    quota_mb: 0,
  });
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"accounts" | "logs">("accounts");
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const create = useMutation({
    mutationFn: () =>
      apiRequest("/ftp/accounts/", {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: () => {
      setForm({ username: "", password: "", relative_directory: "public_html", quota_mb: 0 });
      setError(null);
      setIsCreateOpen(false);
      void qc.invalidateQueries({ queryKey: ["ftp-accounts"] });
      void qc.invalidateQueries({ queryKey: ["ftp-stats"] });
      void qc.invalidateQueries({ queryKey: ["ftp-logs"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const suspend = useMutation({
    mutationFn: ({ id, suspended }: { id: number; suspended: boolean }) =>
      apiRequest(`/ftp/accounts/${id}/suspend/`, {
        method: "POST",
        body: JSON.stringify({ suspended }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["ftp-accounts"] });
      void qc.invalidateQueries({ queryKey: ["ftp-stats"] });
      void qc.invalidateQueries({ queryKey: ["ftp-logs"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiRequest(`/ftp/accounts/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["ftp-accounts"] });
      void qc.invalidateQueries({ queryKey: ["ftp-stats"] });
      void qc.invalidateQueries({ queryKey: ["ftp-logs"] });
    },
  });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Comptes FTP virtuels, suspension, quotas et journaux d’accès."
        stats={[
          { label: "Comptes", value: stats?.accounts_total ?? "—" },
          { label: "Actifs", value: stats?.accounts_active ?? "—" },
          { label: "Suspendus", value: stats?.accounts_suspended ?? "—" },
          { label: "Échecs 24 h", value: stats?.failed_logins_24h ?? "—" },
        ]}
        actions={
          <button type="button" className="vz-btn-primary" onClick={() => setIsCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            Créer un compte
          </button>
        }
      />
      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger dark:border-red-900 dark:bg-red-950/30">
          {error}
        </p>
      )}

      <div className="vz-panel overflow-hidden">
        <Tabs
          tabs={[
            { id: "accounts", label: "Comptes", count: stats?.accounts_total ?? accounts.length, icon: <FolderKey className="h-3.5 w-3.5" /> },
            { id: "logs", label: "Journaux", count: logs.length, icon: <FileText className="h-3.5 w-3.5" /> },
          ]}
          active={tab}
          onChange={(id) => setTab(id as "accounts" | "logs")}
        />
        {tab === "accounts" && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-cp-canvas/80 text-[11px] uppercase tracking-wide text-cp-muted dark:bg-ink-900/80"><tr><th className="px-4 py-2.5">Compte</th><th className="px-4 py-2.5">Répertoire</th><th className="px-4 py-2.5">Quota</th><th className="px-4 py-2.5">État</th><th className="px-4 py-2.5">Dernière connexion</th><th className="px-4 py-2.5 text-right">Actions</th></tr></thead>
              <tbody>
                {isLoading && <tr><td className="px-4 py-8 text-cp-muted" colSpan={6}>Chargement…</td></tr>}
                {!isLoading && accounts.length === 0 && <tr><td colSpan={6}><EmptyState icon={<FolderKey className="h-8 w-8" />} message="Aucun compte FTP." action={<button type="button" className="vz-btn-primary" onClick={() => setIsCreateOpen(true)}><Plus className="h-4 w-4" />Créer un compte</button>} /></td></tr>}
                {accounts.map((acc) => <tr key={acc.id} className="border-t border-cp-border/80 transition hover:bg-cp-canvas/50 dark:border-ink-800 dark:hover:bg-ink-900/40"><td className="px-4 py-3 font-mono text-xs">{acc.username}</td><td className="px-4 py-3">{acc.relative_directory}</td><td className="px-4 py-3">{acc.quota_mb ? `${acc.quota_mb} Mo` : "—"}</td><td className="px-4 py-3"><StatusDot status={acc.status} /></td><td className="px-4 py-3 text-xs text-cp-muted">{acc.last_login_at ? `${new Date(acc.last_login_at).toLocaleString("fr-FR")} (${acc.last_login_ip ?? "—"})` : "—"}</td><td className="px-4 py-3"><div className="flex justify-end gap-0.5"><IconAction label={acc.is_suspended ? "Réactiver" : "Suspendre"} onClick={() => suspend.mutate({ id: acc.id, suspended: !acc.is_suspended })}>{acc.is_suspended ? <PlayCircle className="h-4 w-4" /> : <PauseCircle className="h-4 w-4" />}</IconAction><IconAction label="Supprimer" danger onClick={() => { if (window.confirm(`Supprimer ${acc.username} ?`)) remove.mutate(acc.id); }}><Trash2 className="h-4 w-4" /></IconAction></div></td></tr>)}
              </tbody>
            </table>
          </div>
        )}
        {tab === "logs" && (
          <div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-cp-canvas/80 text-[11px] uppercase tracking-wide text-cp-muted dark:bg-ink-900/80"><tr><th className="px-4 py-2.5">Date</th><th className="px-4 py-2.5">Événement</th><th className="px-4 py-2.5">Utilisateur</th><th className="px-4 py-2.5">IP</th><th className="px-4 py-2.5">Message</th></tr></thead><tbody>{logs.length === 0 && <tr><td colSpan={5}><EmptyState icon={<FileText className="h-8 w-8" />} message="Aucun journal pour le moment." /></td></tr>}{logs.map((log) => <tr key={log.id} className="border-t border-cp-border/80 dark:border-ink-800"><td className="px-4 py-3 text-xs">{new Date(log.created_at).toLocaleString("fr-FR")}</td><td className="px-4 py-3 font-mono text-xs">{log.event_type}</td><td className="px-4 py-3">{log.username}</td><td className="px-4 py-3">{log.ip_address ?? "—"}</td><td className={`px-4 py-3 ${log.success ? "" : "text-cp-danger"}`}>{log.message || log.path || "—"}</td></tr>)}</tbody></table></div>
        )}
      </div>
      {isCreateOpen && <Modal title="Nouveau compte FTP" subtitle="Créez un accès limité à un répertoire." onClose={() => setIsCreateOpen(false)}><form className="space-y-3" onSubmit={onCreate}><div><label className="mb-1 block text-xs font-medium text-cp-muted">Identifiant</label><input className="vz-input" placeholder="web" required autoFocus value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div><div><label className="mb-1 block text-xs font-medium text-cp-muted">Mot de passe</label><input className="vz-input" type="password" required minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div><div><label className="mb-1 block text-xs font-medium text-cp-muted">Répertoire</label><input className="vz-input" value={form.relative_directory} onChange={(e) => setForm({ ...form, relative_directory: e.target.value })} /></div><div><label className="mb-1 block text-xs font-medium text-cp-muted">Quota (Mo, 0 = illimité)</label><input className="vz-input" type="number" min={0} value={form.quota_mb} onChange={(e) => setForm({ ...form, quota_mb: Number(e.target.value) })} /></div><div className="flex justify-end gap-2"><button type="button" className="vz-btn-ghost" onClick={() => setIsCreateOpen(false)}>Annuler</button><button className="vz-btn-primary" type="submit" disabled={create.isPending}>{create.isPending ? "Création…" : "Créer"}</button></div></form></Modal>}
    </div>
  );
}
