import { FormEvent, useEffect, useState, type ChangeEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Power, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { HostingPackage } from "@/types";

type PackageForm = {
  name: string;
  description: string;
  package_type: "client" | "reseller";
  disk_mb: number;
  bandwidth_mb: number;
  unlimited_disk: boolean;
  unlimited_bandwidth: boolean;
  domains: number;
  emails: number;
  databases: number;
  ftp_accounts: number;
  python_apps: number;
  node_apps: number;
  docker_containers: number;
  allow_backup: boolean;
  allow_ssh: boolean;
  allow_dns: boolean;
  allow_ssl: boolean;
  allow_git: boolean;
  max_accounts: number;
  is_active: boolean;
  is_default: boolean;
};

const defaultForm = (): PackageForm => ({
  name: "",
  description: "",
  package_type: "client",
  disk_mb: 10240,
  bandwidth_mb: 102400,
  unlimited_disk: false,
  unlimited_bandwidth: false,
  domains: 1,
  emails: 10,
  databases: 5,
  ftp_accounts: 5,
  python_apps: 1,
  node_apps: 1,
  docker_containers: 0,
  allow_backup: true,
  allow_ssh: false,
  allow_dns: true,
  allow_ssl: true,
  allow_git: true,
  max_accounts: 0,
  is_active: true,
  is_default: false,
});

function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`block space-y-1 ${className}`}>
      <span className="text-xs font-medium text-cp-muted">{label}</span>
      {children}
    </label>
  );
}

function IconAction({
  label,
  onClick,
  danger,
  children,
}: {
  label: string;
  onClick: () => void;
  danger?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent transition
        hover:border-cp-border hover:bg-cp-canvas
        ${danger ? "text-cp-danger hover:bg-red-50" : "text-cp-link hover:text-cp-navy"}`}
    >
      {children}
    </button>
  );
}

function packageToForm(pkg: HostingPackage): PackageForm {
  return {
    name: pkg.name,
    description: pkg.description ?? "",
    package_type: pkg.package_type,
    disk_mb: pkg.disk_mb,
    bandwidth_mb: pkg.bandwidth_mb,
    unlimited_disk: Boolean(pkg.unlimited_disk),
    unlimited_bandwidth: Boolean(pkg.unlimited_bandwidth),
    domains: pkg.domains,
    emails: pkg.emails,
    databases: pkg.databases,
    ftp_accounts: pkg.ftp_accounts,
    python_apps: pkg.python_apps,
    node_apps: pkg.node_apps,
    docker_containers: pkg.docker_containers,
    allow_backup: pkg.allow_backup ?? true,
    allow_ssh: pkg.allow_ssh ?? false,
    allow_dns: pkg.allow_dns ?? true,
    allow_ssl: pkg.allow_ssl ?? true,
    allow_git: pkg.allow_git ?? true,
    max_accounts: pkg.max_accounts ?? 0,
    is_active: pkg.is_active,
    is_default: pkg.is_default,
  };
}

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
    setForm(packageToForm(pkg));
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

  const setNum =
    (key: keyof PackageForm) =>
    (e: ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [key]: Number(e.target.value) });

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <h1 className="text-xl font-semibold text-cp-text">Packages</h1>
          <p className="text-sm text-cp-muted">
            Plans de ressources (disque, mails, BDD, apps, backups…) assignables aux comptes.
          </p>
        </div>
        <button className="vz-btn-ghost" type="button" onClick={() => seed.mutate()}>
          Charger packages système
        </button>
      </div>

      <form className="vz-panel space-y-4 p-4" onSubmit={onSubmit}>
        {editingId != null && (
          <div className="flex items-center justify-between rounded-lg bg-cp-link-soft px-3 py-2 text-sm text-cp-navy">
            <span>Modification du package #{editingId}</span>
            <button type="button" className="underline" onClick={cancelEdit}>
              Annuler
            </button>
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Nom" className="md:col-span-2">
            <input
              className="vz-input w-full"
              placeholder="ex: Basique"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Type">
            <select
              className="vz-input w-full"
              value={form.package_type}
              onChange={(e) =>
                setForm({ ...form, package_type: e.target.value as "client" | "reseller" })
              }
            >
              <option value="client">Client</option>
              <option value="reseller">Revendeur</option>
            </select>
          </Field>
          <Field label="Description" className="md:col-span-3">
            <input
              className="vz-input w-full"
              placeholder="Description courte (optionnel)"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </Field>
        </div>

        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-cp-muted">
            Ressources
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Disque (Mo)">
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                disabled={form.unlimited_disk}
                value={form.disk_mb}
                onChange={setNum("disk_mb")}
              />
            </Field>
            <Field label="Bande passante (Mo)">
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                disabled={form.unlimited_bandwidth}
                value={form.bandwidth_mb}
                onChange={setNum("bandwidth_mb")}
              />
            </Field>
            <label className="flex items-end gap-2 pb-2 text-sm">
              <input
                type="checkbox"
                checked={form.unlimited_disk}
                onChange={(e) => setForm({ ...form, unlimited_disk: e.target.checked })}
              />
              Disque illimité
            </label>
            <label className="flex items-end gap-2 pb-2 text-sm">
              <input
                type="checkbox"
                checked={form.unlimited_bandwidth}
                onChange={(e) => setForm({ ...form, unlimited_bandwidth: e.target.checked })}
              />
              BP illimitée
            </label>
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-cp-muted">
            Limites services
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Domaines">
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                value={form.domains}
                onChange={setNum("domains")}
              />
            </Field>
            <Field label="Comptes e-mail">
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                value={form.emails}
                onChange={setNum("emails")}
              />
            </Field>
            <Field label="Bases de données">
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                value={form.databases}
                onChange={setNum("databases")}
              />
            </Field>
            <Field label="Comptes FTP">
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                value={form.ftp_accounts}
                onChange={setNum("ftp_accounts")}
              />
            </Field>
            <Field label="Apps Python">
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                value={form.python_apps}
                onChange={setNum("python_apps")}
              />
            </Field>
            <Field label="Apps Node.js">
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                value={form.node_apps}
                onChange={setNum("node_apps")}
              />
            </Field>
            <Field label="Conteneurs Docker">
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                value={form.docker_containers}
                onChange={setNum("docker_containers")}
              />
            </Field>
            {form.package_type === "reseller" && (
              <Field label="Comptes max (revendeur)">
                <input
                  className="vz-input w-full"
                  type="number"
                  min={0}
                  value={form.max_accounts}
                  onChange={setNum("max_accounts")}
                  title="0 = illimité"
                />
              </Field>
            )}
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-cp-muted">
            Options
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
            {(
              [
                ["allow_backup", "Backups"],
                ["allow_ssl", "SSL"],
                ["allow_dns", "DNS"],
                ["allow_git", "Git"],
                ["allow_ssh", "SSH"],
                ["is_active", "Actif"],
                ["is_default", "Par défaut"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={Boolean(form[key])}
                  onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
                />
                {label}
              </label>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            className="vz-btn-primary"
            type="submit"
            disabled={create.isPending || update.isPending}
          >
            {editingId != null ? "Enregistrer" : "Créer le package"}
          </button>
          {editingId != null && (
            <button type="button" className="vz-btn-ghost" onClick={cancelEdit}>
              Annuler
            </button>
          )}
        </div>
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
              <th className="px-3 py-2">BP</th>
              <th className="px-3 py-2">Dom.</th>
              <th className="px-3 py-2">Mail</th>
              <th className="px-3 py-2">BDD</th>
              <th className="px-3 py-2">FTP</th>
              <th className="px-3 py-2">Py/Node</th>
              <th className="px-3 py-2">Docker</th>
              <th className="px-3 py-2">Backup</th>
              <th className="px-3 py-2">Comptes</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={13}>
                  Chargement…
                </td>
              </tr>
            )}
            {packages.map((pkg) => (
              <tr key={pkg.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-medium">
                  {pkg.name}
                  {!pkg.is_active && (
                    <span className="ml-2 text-[10px] uppercase text-cp-muted">off</span>
                  )}
                  {pkg.is_default ? (
                    <span className="ml-2 rounded bg-cp-orange-soft px-1.5 text-[10px] text-cp-orange-dark">
                      défaut
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-2 capitalize">{pkg.package_type}</td>
                <td className="px-3 py-2">
                  {pkg.unlimited_disk ? "∞" : `${pkg.disk_mb}`}
                </td>
                <td className="px-3 py-2">
                  {pkg.unlimited_bandwidth ? "∞" : `${pkg.bandwidth_mb}`}
                </td>
                <td className="px-3 py-2">{pkg.domains}</td>
                <td className="px-3 py-2">{pkg.emails}</td>
                <td className="px-3 py-2">{pkg.databases}</td>
                <td className="px-3 py-2">{pkg.ftp_accounts}</td>
                <td className="px-3 py-2">
                  {pkg.python_apps}/{pkg.node_apps}
                </td>
                <td className="px-3 py-2">{pkg.docker_containers}</td>
                <td className="px-3 py-2">{pkg.allow_backup ? "oui" : "non"}</td>
                <td className="px-3 py-2">{pkg.assigned_count ?? 0}</td>
                <td className="px-3 py-2">
                  <div className="flex justify-end gap-1">
                    <IconAction label="Modifier" onClick={() => setEditingId(pkg.id)}>
                      <Pencil className="h-4 w-4" />
                    </IconAction>
                    <IconAction
                      label={pkg.is_active ? "Désactiver" : "Activer"}
                      onClick={() => toggleActive.mutate(pkg)}
                    >
                      <Power className="h-4 w-4" />
                    </IconAction>
                    <IconAction
                      label="Supprimer"
                      danger
                      onClick={() => {
                        const used = (pkg.assigned_count ?? 0) > 0;
                        const msg = used
                          ? `Le package « ${pkg.name} » est assigné à ${pkg.assigned_count} compte(s). Il sera désactivé (pas supprimé). Continuer ?`
                          : `Supprimer définitivement le package « ${pkg.name} » ?`;
                        if (window.confirm(msg)) remove.mutate(pkg.id);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </IconAction>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && packages.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={13}>
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
