import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

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

  const create = useMutation({
    mutationFn: () =>
      apiRequest("/ftp/accounts/", {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: () => {
      setForm({ username: "", password: "", relative_directory: "public_html", quota_mb: 0 });
      setError(null);
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
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-cp-muted">
          Comptes FTP virtuels, suspension, quotas et journaux d&apos;accès.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Comptes", value: stats?.accounts_total ?? "—" },
          { label: "Actifs", value: stats?.accounts_active ?? "—" },
          { label: "Suspendus", value: stats?.accounts_suspended ?? "—" },
          { label: "Échecs 24h", value: stats?.failed_logins_24h ?? "—" },
        ].map((card) => (
          <div key={card.label} className="vz-panel p-4">
            <p className="text-xs font-semibold uppercase text-cp-muted">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold text-cp-orange">{card.value}</p>
          </div>
        ))}
      </div>

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-5" onSubmit={onCreate}>
        <input
          className="vz-input"
          placeholder="login (ex: web)"
          required
          value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })}
        />
        <input
          className="vz-input"
          type="password"
          placeholder="mot de passe"
          required
          minLength={8}
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
        <input
          className="vz-input"
          placeholder="répertoire"
          value={form.relative_directory}
          onChange={(e) => setForm({ ...form, relative_directory: e.target.value })}
        />
        <input
          className="vz-input"
          type="number"
          min={0}
          title="Quota Mo"
          value={form.quota_mb}
          onChange={(e) => setForm({ ...form, quota_mb: Number(e.target.value) })}
        />
        <button className="vz-btn-primary" type="submit" disabled={create.isPending}>
          Créer compte FTP
        </button>
      </form>
      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">{error}</p>
      )}

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Compte</th>
              <th className="px-3 py-2">Répertoire</th>
              <th className="px-3 py-2">Quota</th>
              <th className="px-3 py-2">État</th>
              <th className="px-3 py-2">Dernière connexion</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={6}>
                  Chargement…
                </td>
              </tr>
            )}
            {accounts.map((acc) => (
              <tr key={acc.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-mono text-xs">{acc.username}</td>
                <td className="px-3 py-2">{acc.relative_directory}</td>
                <td className="px-3 py-2">{acc.quota_mb ? `${acc.quota_mb} Mo` : "—"}</td>
                <td className="px-3 py-2">
                  <span
                    className={
                      acc.status === "active"
                        ? "text-cp-success"
                        : acc.status === "suspended"
                          ? "text-cp-danger"
                          : "text-cp-muted"
                    }
                  >
                    {acc.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs text-cp-muted">
                  {acc.last_login_at
                    ? `${new Date(acc.last_login_at).toLocaleString("fr-FR")} (${acc.last_login_ip ?? "—"})`
                    : "—"}
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() =>
                        suspend.mutate({ id: acc.id, suspended: !acc.is_suspended })
                      }
                    >
                      {acc.is_suspended ? "Réactiver" : "Suspendre"}
                    </button>
                    <button
                      type="button"
                      className="text-cp-danger hover:underline"
                      onClick={() => {
                        if (window.confirm(`Supprimer ${acc.username} ?`)) remove.mutate(acc.id);
                      }}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && accounts.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={6}>
                  Aucun compte FTP.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="vz-panel overflow-x-auto">
        <div className="border-b border-cp-border bg-cp-canvas px-3 py-2 text-xs font-semibold uppercase text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          Journaux FTP
        </div>
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="text-xs uppercase text-cp-muted">
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Événement</th>
              <th className="px-3 py-2">User</th>
              <th className="px-3 py-2">IP</th>
              <th className="px-3 py-2">Message</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 text-xs">
                  {new Date(log.created_at).toLocaleString("fr-FR")}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{log.event_type}</td>
                <td className="px-3 py-2">{log.username}</td>
                <td className="px-3 py-2">{log.ip_address ?? "—"}</td>
                <td className={`px-3 py-2 ${log.success ? "" : "text-cp-danger"}`}>
                  {log.message || log.path || "—"}
                </td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Aucun journal pour le moment.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
