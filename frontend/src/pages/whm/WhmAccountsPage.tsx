import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

const emptyCreate = {
  email: "",
  username: "",
  password: "",
  domain: "",
  role: "client",
  package_id: "",
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

  const [form, setForm] = useState(emptyCreate);
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
    void qc.invalidateQueries({ queryKey: ["domains"] });
  };

  const createUser = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        email: form.email,
        username: form.username,
        password: form.password,
        role: form.role,
        domain: form.domain.trim().toLowerCase(),
      };
      if (form.package_id) {
        payload.package_id = Number(form.package_id);
      }
      return apiRequest<User>("/auth/users/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      setError(null);
      invalidate();
      setForm(emptyCreate);
    },
    onError: (err: Error) => setError(err.message || "Création impossible."),
  });

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
      if (editForm.password.trim()) {
        payload.password = editForm.password.trim();
      }
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

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createUser.mutate();
  }

  function onSaveEdit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    updateUser.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold text-cp-text">Create a New Account</h1>
        <p className="text-sm text-cp-muted">
          Comme cPanel : username + domaine principal → home,{" "}
          <code className="font-mono text-xs">public_html</code>, zone DNS et vhost nginx.
        </p>
      </div>

      <form className="vz-panel grid gap-3 p-4 md:grid-cols-2 lg:grid-cols-3" onSubmit={onSubmit}>
        <label className="space-y-1">
          <span className="text-[11px] font-medium text-cp-muted">Username *</span>
          <input
            className="vz-input"
            placeholder="ex: johndoe"
            required
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
        </label>
        <label className="space-y-1 lg:col-span-2">
          <span className="text-[11px] font-medium text-cp-muted">Domain *</span>
          <input
            className="vz-input"
            placeholder="exemple.com"
            required
            value={form.domain}
            onChange={(e) => setForm({ ...form, domain: e.target.value })}
          />
          <span className="text-[11px] text-cp-muted">
            Domaine principal → <code className="font-mono">~/public_html</code> + DNS A + nginx
          </span>
        </label>
        <label className="space-y-1 lg:col-span-2">
          <span className="text-[11px] font-medium text-cp-muted">Email *</span>
          <input
            className="vz-input"
            type="email"
            placeholder="email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] font-medium text-cp-muted">Password *</span>
          <input
            className="vz-input"
            type="password"
            placeholder="mot de passe"
            required
            minLength={10}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] font-medium text-cp-muted">Package</span>
          <select
            className="vz-input"
            value={form.package_id}
            onChange={(e) => setForm({ ...form, package_id: e.target.value })}
          >
            <option value="">Package…</option>
            {packages.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-end">
          <button className="vz-btn-primary w-full" type="submit" disabled={createUser.isPending}>
            Créer le compte
          </button>
        </div>
      </form>

      {editing && editForm && (
        <form className="vz-panel space-y-3 border-cp-link/30 p-4" onSubmit={onSaveEdit}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold text-cp-navy">
              Modifier <span className="font-mono">{editing.username}</span>
              {editing.primary_domain && (
                <span className="ml-2 text-sm font-normal text-cp-muted">
                  ({editing.primary_domain})
                </span>
              )}
            </h2>
            <button type="button" className="vz-btn-ghost" onClick={() => setEditing(null)}>
              Annuler
            </button>
          </div>
          <div className="grid gap-2 md:grid-cols-3">
            <input
              className="vz-input md:col-span-2"
              type="email"
              required
              value={editForm.email}
              onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
              placeholder="email"
            />
            <select
              className="vz-input"
              value={editForm.role}
              onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
            >
              <option value="client">Client</option>
              <option value="reseller">Revendeur</option>
            </select>
            <input
              className="vz-input"
              placeholder="Prénom"
              value={editForm.first_name}
              onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
            />
            <input
              className="vz-input"
              placeholder="Nom"
              value={editForm.last_name}
              onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
            />
            <input
              className="vz-input"
              type="password"
              minLength={10}
              placeholder="Nouveau mot de passe (optionnel)"
              value={editForm.password}
              onChange={(e) => setEditForm({ ...editForm, password: e.target.value })}
            />
            <select
              className="vz-input"
              value={editForm.package_id}
              onChange={(e) => setEditForm({ ...editForm, package_id: e.target.value })}
            >
              <option value="">Package (inchangé)…</option>
              {packages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm text-cp-text">
              <input
                type="checkbox"
                checked={editForm.is_active}
                onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
              />
              Compte actif
            </label>
            <button className="vz-btn-primary" type="submit" disabled={updateUser.isPending}>
              Enregistrer
            </button>
          </div>
        </form>
      )}

      {error && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
          {error}
        </p>
      )}

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Compte</th>
              <th className="px-3 py-2">Domaine</th>
              <th className="px-3 py-2">E-mail</th>
              <th className="px-3 py-2">Rôle</th>
              <th className="px-3 py-2">État</th>
              <th className="px-3 py-2">Disque</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={7}>
                  Chargement…
                </td>
              </tr>
            )}
            {users.map((u) => (
              <tr key={u.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-medium">{u.username}</td>
                <td className="px-3 py-2 font-mono text-xs text-cp-navy dark:text-ink-200">
                  {u.primary_domain || "—"}
                </td>
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2 capitalize">{u.role}</td>
                <td className="px-3 py-2">
                  {u.is_suspended ? "suspendu" : u.is_active ? "actif" : "inactif"}
                </td>
                <td className="px-3 py-2">
                  {u.quota?.unlimited_disk ? "∞" : `${u.quota?.disk_mb ?? "—"} Mo`}
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => setEditing(u)}
                    >
                      Modifier
                    </button>
                    <button
                      type="button"
                      className="text-cp-muted hover:underline"
                      onClick={() =>
                        suspendUser.mutate({ id: u.id, suspended: !u.is_suspended })
                      }
                    >
                      {u.is_suspended ? "Réactiver" : "Suspendre"}
                    </button>
                    <button
                      type="button"
                      className="text-cp-danger hover:underline"
                      onClick={() => {
                        if (
                          window.confirm(
                            `Supprimer le compte « ${u.username} » et son home ? Cette action est irréversible.`,
                          )
                        ) {
                          deleteUser.mutate(u.id);
                        }
                      }}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && users.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={7}>
                  Aucun compte.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
