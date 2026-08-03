import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import type { HostingPackage } from "@/types";

export function WhmPackagesPage() {
  const qc = useQueryClient();
  const { data: packages = [], isLoading } = useQuery({
    queryKey: ["packages"],
    queryFn: () => apiRequest<HostingPackage[]>("/packages/"),
  });

  const [form, setForm] = useState({
    name: "",
    package_type: "client" as "client" | "reseller",
    disk_mb: 10240,
    domains: 1,
    emails: 10,
    databases: 5,
  });
  const [error, setError] = useState<string | null>(null);

  const seed = useMutation({
    mutationFn: () => apiRequest("/packages/seed/", { method: "POST", body: "{}" }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["packages"] });
    },
    onError: (err: Error) => setError(err.message || "Échec du seed."),
  });

  const create = useMutation({
    mutationFn: () =>
      apiRequest("/packages/", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          bandwidth_mb: form.disk_mb * 10,
          ftp_accounts: 5,
          python_apps: 1,
          node_apps: 1,
        }),
      }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["packages"] });
      setForm((f) => ({ ...f, name: "" }));
    },
    onError: (err: Error) => setError(err.message || "Création impossible."),
  });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    create.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <h1 className="text-xl font-semibold text-cp-text">Packages</h1>
          <p className="text-sm text-cp-muted">
            Plans de ressources synchronisés avec les quotas comptes.
          </p>
        </div>
        <button className="vz-btn-ghost" type="button" onClick={() => seed.mutate()}>
          Charger packages système
        </button>
      </div>

      <form className="vz-panel grid gap-3 p-4 md:grid-cols-6" onSubmit={onCreate}>
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
        />
        <input
          className="vz-input"
          type="number"
          min={0}
          value={form.domains}
          onChange={(e) => setForm({ ...form, domains: Number(e.target.value) })}
          title="Domaines"
        />
        <button className="vz-btn-primary" type="submit" disabled={create.isPending}>
          Créer
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
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={8}>
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
