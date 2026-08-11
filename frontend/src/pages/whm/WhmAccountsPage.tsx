import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Search, UserPlus } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { HostingPackage, User } from "@/types";

type EditForm = {
  email: string;
  first_name: string;
  last_name: string;
  password: string;
  role: string;
  package_id: string;
  is_active: boolean;
};

export function WhmAccountsPage() {
  const qc = useQueryClient();
  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: async () => {
      const raw = await apiRequest<User[] | { results: User[] }>("/auth/users/");
      return Array.isArray(raw) ? raw : raw.results;
    },
  });
  const { data: packages = [] } = useQuery({
    queryKey: ["packages", "client"],
    queryFn: () => apiRequest<HostingPackage[]>("/packages/?type=client"),
  });

  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<User | null>(null);
  const [editForm, setEditForm] = useState<EditForm | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) {
      setEditForm(null);
      return;
    }
    setEditForm({
      email: editing.email,
      first_name: editing.first_name || "",
      last_name: editing.last_name || "",
      password: "",
      role: editing.role,
      package_id: "",
      is_active: editing.is_active && !editing.is_suspended,
    });
  }, [editing]);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["users"] });
    void qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
  };

  const updateUser = useMutation({
    mutationFn: async () => {
      if (!editing || !editForm) return;
      const payload: Record<string, unknown> = {
        email: editForm.email,
        first_name: editForm.first_name,
        last_name: editForm.last_name,
        role: editForm.role,
        is_active: editForm.is_active,
        is_suspended: !editForm.is_active,
      };
      if (editForm.password.trim()) payload.password = editForm.password.trim();
      await apiRequest(`/auth/users/${editing.id}/`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      if (editForm.package_id) {
        await apiRequest("/packages/assign/", {
          method: "POST",
          body: JSON.stringify({
            user_id: editing.id,
            package_id: Number(editForm.package_id),
          }),
        });
      }
    },
    onSuccess: () => {
      setError(null);
      setEditing(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Modification impossible."),
  });

  const suspendUser = useMutation({
    mutationFn: ({ id, suspended }: { id: number; suspended: boolean }) =>
      apiRequest(`/auth/users/${id}/suspend/`, {
        method: "POST",
        body: JSON.stringify({ suspended }),
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Action impossible."),
  });

  const deleteUser = useMutation({
    mutationFn: (id: number) => apiRequest(`/auth/users/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      setError(null);
      if (editing) setEditing(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Suppression impossible."),
  });

  const filtered = users.filter((u) => {
    const s = q.trim().toLowerCase();
    if (!s) return true;
    return (
      u.username.toLowerCase().includes(s) ||
      u.email.toLowerCase().includes(s) ||
      (u.primary_domain || "").toLowerCase().includes(s)
    );
  });

  function onSaveEdit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    updateUser.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="whm-page-head">
        <div className="whm-page-head-bar flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-sm font-semibold uppercase tracking-wide">List Accounts</h1>
          <Link to="/whm/accounts/create" className="whm-btn-create !py-1.5 text-xs">
            <UserPlus className="h-3.5 w-3.5" />
            Create a New Account
          </Link>
        </div>
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cp-muted" />
            <input
              className="vz-input pl-9"
              placeholder="Search by user, domain, email…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <p className="text-xs text-cp-muted">
            {filtered.length} account{filtered.length === 1 ? "" : "s"}
          </p>
        </div>
      </div>

      {editing && editForm && (
        <form
          className="overflow-hidden rounded-lg border border-cp-link/30 bg-white shadow-panel dark:border-ink-700 dark:bg-ink-950"
          onSubmit={onSaveEdit}
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cp-border bg-cp-header px-4 py-2 text-white dark:border-ink-800">
            <h2 className="text-sm font-semibold">
              Modify Account · <span className="font-mono">{editing.username}</span>
            </h2>
            <button type="button" className="text-sm text-white/80 hover:text-white" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
          <div className="grid gap-3 p-4 md:grid-cols-3">
            <input
              className="vz-input md:col-span-2"
              type="email"
              required
              value={editForm.email}
              onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
            />
            <select
              className="vz-input"
              value={editForm.role}
              onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
            >
              <option value="client">Client</option>
              <option value="reseller">Reseller</option>
            </select>
            <input
              className="vz-input"
              placeholder="First name"
              value={editForm.first_name}
              onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
            />
            <input
              className="vz-input"
              placeholder="Last name"
              value={editForm.last_name}
              onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
            />
            <input
              className="vz-input"
              type="password"
              minLength={10}
              placeholder="New password (optional)"
              value={editForm.password}
              onChange={(e) => setEditForm({ ...editForm, password: e.target.value })}
            />
            <select
              className="vz-input"
              value={editForm.package_id}
              onChange={(e) => setEditForm({ ...editForm, package_id: e.target.value })}
            >
              <option value="">Package (unchanged)…</option>
              {packages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={editForm.is_active}
                onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
              />
              Active
            </label>
            <button className="whm-btn-create" type="submit" disabled={updateUser.isPending}>
              Save
            </button>
          </div>
        </form>
      )}

      {error && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
          {error}
        </p>
      )}

      <div className="vz-table-wrap overflow-hidden rounded-lg border border-cp-border bg-white shadow-panel dark:border-ink-800 dark:bg-ink-950">
        <table className="min-w-[40rem] w-full text-left text-sm">
          <thead className="bg-cp-canvas text-[11px] uppercase tracking-wide text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2.5">Domain</th>
              <th className="px-3 py-2.5">User</th>
              <th className="px-3 py-2.5">Email</th>
              <th className="px-3 py-2.5">Role</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-3 py-2.5">Disk</th>
              <th className="px-3 py-2.5">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-6 text-cp-muted" colSpan={7}>
                  Loading…
                </td>
              </tr>
            )}
            {filtered.map((u) => (
              <tr key={u.id} className="border-t border-cp-border/80 hover:bg-cp-orange-soft/40 dark:border-ink-800 dark:hover:bg-ink-900/50">
                <td className="px-3 py-2.5">
                  {u.primary_domain ? (
                    <a
                      href={`http://${u.primary_domain}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 font-mono text-xs text-cp-link hover:underline"
                    >
                      {u.primary_domain}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : (
                    <span className="text-cp-muted">—</span>
                  )}
                </td>
                <td className="px-3 py-2.5 font-medium">{u.username}</td>
                <td className="px-3 py-2.5 text-cp-muted">{u.email}</td>
                <td className="px-3 py-2.5 capitalize">{u.role}</td>
                <td className="px-3 py-2.5">
                  <span
                    className={
                      u.is_suspended
                        ? "text-cp-danger"
                        : u.is_active
                          ? "text-cp-success"
                          : "text-cp-muted"
                    }
                  >
                    {u.is_suspended ? "suspended" : u.is_active ? "active" : "inactive"}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  {u.quota?.unlimited_disk ? "∞" : `${u.quota?.disk_mb ?? "—"} MB`}
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex flex-wrap gap-2 text-xs">
                    <button type="button" className="text-cp-link hover:underline" onClick={() => setEditing(u)}>
                      Modify
                    </button>
                    <button
                      type="button"
                      className="text-cp-muted hover:underline"
                      onClick={() => suspendUser.mutate({ id: u.id, suspended: !u.is_suspended })}
                    >
                      {u.is_suspended ? "Unsuspend" : "Suspend"}
                    </button>
                    <button
                      type="button"
                      className="text-cp-danger hover:underline"
                      onClick={() => {
                        if (
                          window.confirm(
                            `Delete account « ${u.username} » and its home directory? This cannot be undone.`,
                          )
                        ) {
                          deleteUser.mutate(u.id);
                        }
                      }}
                    >
                      Terminate
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td className="px-3 py-8 text-center text-cp-muted" colSpan={7}>
                  No accounts.{" "}
                  <Link to="/whm/accounts/create" className="text-cp-link hover:underline">
                    Create a New Account
                  </Link>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
