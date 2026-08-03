import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import type { HostingPackage, User } from "@/types";

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

  const [form, setForm] = useState({
    email: "",
    username: "",
    password: "",
    role: "client",
    package_id: "",
  });
  const [error, setError] = useState<string | null>(null);

  const createUser = useMutation({
    mutationFn: async () => {
      const user = await apiRequest<User>("/auth/users/", {
        method: "POST",
        body: JSON.stringify({
          email: form.email,
          username: form.username,
          password: form.password,
          role: form.role,
        }),
      });
      if (form.package_id) {
        await apiRequest("/packages/assign/", {
          method: "POST",
          body: JSON.stringify({
            user_id: user.id,
            package_id: Number(form.package_id),
          }),
        });
      }
      return user;
    },
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["users"] });
      void qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
      setForm({ email: "", username: "", password: "", role: "client", package_id: "" });
    },
    onError: (err: Error) => setError(err.message || "Création impossible."),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createUser.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <h1 className="font-display text-xl font-semibold text-white">Comptes</h1>
        <p className="text-sm text-white/50">
          Création de comptes d&apos;hébergement et assignation de package.
        </p>
      </div>

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-6" onSubmit={onSubmit}>
        <input
          className="vz-input"
          placeholder="username"
          required
          value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })}
        />
        <input
          className="vz-input md:col-span-2"
          type="email"
          placeholder="email"
          required
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
        <input
          className="vz-input"
          type="password"
          placeholder="mot de passe"
          required
          minLength={10}
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
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
        <button className="vz-btn-primary" type="submit" disabled={createUser.isPending}>
          Créer compte
        </button>
      </form>

      {error && (
        <p role="alert" className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2.5 text-sm text-rose-100">
          {error}
        </p>
      )}

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Compte</th>
              <th className="px-3 py-2">E-mail</th>
              <th className="px-3 py-2">Rôle</th>
              <th className="px-3 py-2">État</th>
              <th className="px-3 py-2">Disque</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={5}>
                  Chargement…
                </td>
              </tr>
            )}
            {users.map((u) => (
              <tr key={u.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-medium">{u.username}</td>
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2 capitalize">{u.role}</td>
                <td className="px-3 py-2">
                  {u.is_suspended ? "suspendu" : u.is_active ? "actif" : "inactif"}
                </td>
                <td className="px-3 py-2">
                  {u.quota?.unlimited_disk ? "∞" : `${u.quota?.disk_mb ?? "—"} Mo`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
