import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import type { HostingPackage } from "@/types";

type PackageForm = {
  name: string;
  package_type: "client" | "reseller";
  disk_mb: number;
  domains: number;
  emails: number;
  databases: number;
  bandwidth_mb: number;
  ftp_accounts: number;
  python_apps: number;
  node_apps: number;
  is_active: boolean;
  is_default: boolean;
};

const defaultForm = (): PackageForm => ({
  name: "",
  package_type: "client",
  disk_mb: 10240,
  domains: 1,
  emails: 10,
  databases: 5,
  bandwidth_mb: 102400,
  ftp_accounts: 5,
  python_apps: 1,
  node_apps: 1,
  is_active: true,
  is_default: false,
});

export function WhmPackagesPage() {
  const qc = useQueryClient();
  const { data: packages = [], isLoading } = useQuery({
    queryKey: ["packages"],
    queryFn: () => apiRequest<HostingPackage[]>("/packages/"),
  });

  const [form, setForm] = useState<PackageForm>(defaultForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (editingId == null) return;
    const pkg = packages.find((p) => p.id === editingId);
    if (!pkg) return;
    setForm({
      name: pkg.name,
      package_type: pkg.package_type,
      disk_mb: pkg.disk_mb,
      domains: pkg.domains,
      emails: pkg.emails,
      databases: pkg.databases,
      bandwidth_mb: pkg.bandwidth_mb,
      ftp_accounts: pkg.ftp_accounts,
      python_apps: pkg.python_apps,
      node_apps: pkg.node_apps,
      is_active: pkg.is_active,
      is_default: pkg.is_default,
    });
  }, [editingId, packages]);

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["packages"] });

  const seed = useMutation({
    mutationFn: () => apiRequest("/packages/seed/", { method: "POST", body: "{}" }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Échec du seed."),
  });

  const create = useMutation({
    mutationFn: () =>
      apiRequest("/packages/", {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
      setForm(defaultForm());
    },
    onError: (err: Error) => setError(err.message || "Création impossible."),
  });

  const update = useMutation({
    mutationFn: () => {
      if (editingId == null) throw new Error("Aucun package sélectionné.");
      return apiRequest(`/packages/${editingId}/`, {
        method: "PATCH",
        body: JSON.stringify(form),
      });
    },
    onSuccess: () => {
      setError(null);
      setEditingId(null);
      setForm(defaultForm());
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Modification impossible."),
  });

  const toggleActive = useMutation({
    mutationFn: (pkg: HostingPackage) =>
      apiRequest(`/packages/${pkg.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !pkg.is_active }),
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Action impossible."),
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiRequest(`/packages/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      setError(null);
      if (editingId) {
        setEditingId(null);
        setForm(defaultForm());
      }
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Suppression impossible."),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (editingId != null) update.mutate();
    else create.mutate();
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(defaultForm());
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <h1 className="text-xl font-semibold text-cp-text">Packages</h1>
          <p className="text-sm text-cp-muted">
            Créer, modifier ou supprimer les plans de ressources.
          </p>
        </div>
        <button className="vz-btn-ghost" type="button" onClick={() => seed.mutate()}>
          Charger packages système
        </button>
      </div>

      <form className="vz-panel grid gap-3 p-4 md:grid-cols-6" onSubmit={onSubmit}>
        {editingId != null && (
          <div className="md:col-span-6 flex items-center justify-between rounded-lg bg-cp-link-soft px-3 py-2 text-sm text-cp-navy">
            <span>
              Modification du package #{editingId}
            </span>
            <button type="button" className="underline" onClick={cancelEdit}>
              Annuler
            </button>
          </div>
        )}
        <input
          className="vz-input md:col-span-2"
          placeholder="Nom du package"
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <select
          className="vz-input"
          value={form.package_type}
          onChange={(e) =>
            setForm({ ...form, package_type: e.target.value as "client" | "reseller" })
          }
        >
          <option value="client">Client</option>
          <option value="reseller">Revendeur</option>
        </select>
        <input
          className="vz-input"
          type="number"
          min={0}
          value={form.disk_mb}
          onChange={(e) => setForm({ ...form, disk_mb: Number(e.target.value) })}
          title="Disque Mo"
          placeholder="Disque Mo"
        />
        <input
          className="vz-input"
          type="number"
          min={0}
          value={form.domains}
          onChange={(e) => setForm({ ...form, domains: Number(e.target.value) })}
          title="Domaines"
          placeholder="Domaines"
        />
        <input
          className="vz-input"
          type="number"
          min={0}
          value={form.emails}
          onChange={(e) => setForm({ ...form, emails: Number(e.target.value) })}
          title="E-mails"
          placeholder="E-mails"
        />
        <input
          className="vz-input"
          type="number"
          min={0}
          value={form.databases}
          onChange={(e) => setForm({ ...form, databases: Number(e.target.value) })}
          title="Bases"
          placeholder="BDD"
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
          />
          Actif
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_default}
            onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
          />
          Par défaut
        </label>
        <button
          className="vz-btn-primary md:col-span-2"
          type="submit"
          disabled={create.isPending || update.isPending}
        >
          {editingId != null ? "Enregistrer" : "Créer"}
        </button>
      </form>

      {error && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
          {error}
        </p>
      )}

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Package</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Disque</th>
              <th className="px-3 py-2">Domaines</th>
              <th className="px-3 py-2">E-mails</th>
              <th className="px-3 py-2">BDD</th>
              <th className="px-3 py-2">Comptes</th>
              <th className="px-3 py-2">État</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={9}>
                  Chargement…
                </td>
              </tr>
            )}
            {packages.map((pkg) => (
              <tr key={pkg.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-medium">
                  {pkg.name}
                  {pkg.is_default ? (
                    <span className="ml-2 rounded bg-cp-orange-soft px-1.5 text-[10px] text-cp-orange-dark">
                      défaut
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-2 capitalize">{pkg.package_type}</td>
                <td className="px-3 py-2">
                  {pkg.unlimited_disk ? "∞" : `${pkg.disk_mb} Mo`}
                </td>
                <td className="px-3 py-2">{pkg.domains}</td>
                <td className="px-3 py-2">{pkg.emails}</td>
                <td className="px-3 py-2">{pkg.databases}</td>
                <td className="px-3 py-2">{pkg.assigned_count ?? 0}</td>
                <td className="px-3 py-2">{pkg.is_active ? "actif" : "off"}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() => setEditingId(pkg.id)}
                    >
                      Modifier
                    </button>
                    <button
                      type="button"
                      className="text-cp-muted hover:underline"
                      onClick={() => toggleActive.mutate(pkg)}
                    >
                      {pkg.is_active ? "Désactiver" : "Activer"}
                    </button>
                    <button
                      type="button"
                      className="text-cp-danger hover:underline"
                      onClick={() => {
                        const used = (pkg.assigned_count ?? 0) > 0;
                        const msg = used
                          ? `Le package « ${pkg.name} » est assigné à ${pkg.assigned_count} compte(s). Il sera désactivé (pas supprimé). Continuer ?`
                          : `Supprimer définitivement le package « ${pkg.name} » ?`;
                        if (window.confirm(msg)) remove.mutate(pkg.id);
                      }}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && packages.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={9}>
                  Aucun package.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
