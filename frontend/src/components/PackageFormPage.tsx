import { type ChangeEvent, type FormEvent, type ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Loader2, Package } from "lucide-react";
import type { HostingPackage } from "@/types";

export type PackageForm = {
  name: string;
  description: string;
  package_type: "client" | "reseller";
  disk_mb: number;
  bandwidth_mb: number;
  unlimited_disk: boolean;
  unlimited_bandwidth: boolean;
  cpu_millicores: number;
  ram_mb: number;
  unlimited_cpu: boolean;
  unlimited_ram: boolean;
  inode_limit: number;
  max_processes: number;
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

export function defaultPackageForm(
  packageType: "client" | "reseller" = "client",
): PackageForm {
  return {
    name: "",
    description: "",
    package_type: packageType,
    disk_mb: 10240,
    bandwidth_mb: 102400,
    unlimited_disk: false,
    unlimited_bandwidth: false,
    cpu_millicores: 1000,
    ram_mb: 1024,
    unlimited_cpu: false,
    unlimited_ram: false,
    inode_limit: 200000,
    max_processes: 100,
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
  };
}

export function packageToForm(pkg: HostingPackage): PackageForm {
  return {
    name: pkg.name,
    description: pkg.description ?? "",
    package_type: pkg.package_type,
    disk_mb: pkg.disk_mb,
    bandwidth_mb: pkg.bandwidth_mb,
    unlimited_disk: Boolean(pkg.unlimited_disk),
    unlimited_bandwidth: Boolean(pkg.unlimited_bandwidth),
    cpu_millicores: pkg.cpu_millicores ?? 1000,
    ram_mb: pkg.ram_mb ?? 1024,
    unlimited_cpu: Boolean(pkg.unlimited_cpu),
    unlimited_ram: Boolean(pkg.unlimited_ram),
    inode_limit: pkg.inode_limit ?? 200000,
    max_processes: pkg.max_processes ?? 100,
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

export function PackageFormPage({
  mode,
  initial,
  allowResellerType,
  submitting,
  error,
  onSubmit,
}: {
  mode: "create" | "edit";
  initial: PackageForm;
  allowResellerType: boolean;
  submitting: boolean;
  error: string | null;
  onSubmit: (form: PackageForm) => void;
}) {
  const [form, setForm] = useState<PackageForm>(initial);

  const setNum =
    (key: keyof PackageForm) =>
    (e: ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [key]: Number(e.target.value) });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit(form);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 animate-fade-up">
      <div className="whm-page-head">
        <div className="whm-page-head-bar flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Package className="h-4 w-4 text-cp-orange" />
            <h1 className="text-sm font-semibold uppercase tracking-wide">
              {mode === "create" ? "Add a Package" : "Edit a Package"}
            </h1>
          </div>
          <Link
            to="/whm/packages"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-cp-link hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Liste des packages
          </Link>
        </div>
        <p className="px-4 py-3 text-sm text-cp-muted">
          {mode === "create"
            ? "Définissez les limites du plan (disque, e-mails, bases…). Les packages revendeur fixent aussi le plafond de comptes."
            : "Modifiez les limites du plan. Les comptes déjà assignés conserveront le package jusqu’à réassignation."}
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger"
        >
          {error}
        </p>
      )}

      <form
        className="overflow-hidden rounded-lg border border-cp-border bg-white shadow-panel dark:border-ink-800 dark:bg-ink-950"
        onSubmit={handleSubmit}
      >
        <div className="border-b border-cp-border bg-cp-canvas/60 px-4 py-2 text-xs font-bold uppercase tracking-wide text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          Identité
        </div>
        <div className="grid gap-3 p-4 md:grid-cols-3">
          <Field label="Nom" className="md:col-span-2">
            <input
              className="vz-input w-full"
              placeholder="ex: Basique"
              required
              autoFocus
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Type">
            <select
              className="vz-input w-full"
              value={form.package_type}
              disabled={!allowResellerType}
              onChange={(e) =>
                setForm({
                  ...form,
                  package_type: e.target.value as "client" | "reseller",
                })
              }
            >
              <option value="client">Client</option>
              {allowResellerType && <option value="reseller">Revendeur</option>}
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

        <div className="border-y border-cp-border bg-cp-canvas/60 px-4 py-2 text-xs font-bold uppercase tracking-wide text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          Ressources
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
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
              onChange={(e) =>
                setForm({ ...form, unlimited_bandwidth: e.target.checked })
              }
            />
            BP illimitée
          </label>
        </div>

        <div className="border-y border-cp-border bg-cp-canvas/60 px-4 py-2 text-xs font-bold uppercase tracking-wide text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          V-zone Pulse (CPU / RAM / processus / inodes)
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="CPU (millicores, 1000 = 1 cœur)">
            <input
              className="vz-input w-full"
              type="number"
              min={0}
              disabled={form.unlimited_cpu}
              value={form.cpu_millicores}
              onChange={setNum("cpu_millicores")}
            />
          </Field>
          <Field label="RAM (Mo)">
            <input
              className="vz-input w-full"
              type="number"
              min={0}
              disabled={form.unlimited_ram}
              value={form.ram_mb}
              onChange={setNum("ram_mb")}
            />
          </Field>
          <Field label="Processus max (TasksMax)">
            <input
              className="vz-input w-full"
              type="number"
              min={1}
              value={form.max_processes}
              onChange={setNum("max_processes")}
            />
          </Field>
          <Field label="Inodes max">
            <input
              className="vz-input w-full"
              type="number"
              min={0}
              value={form.inode_limit}
              onChange={setNum("inode_limit")}
            />
          </Field>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={form.unlimited_cpu}
              onChange={(e) => setForm({ ...form, unlimited_cpu: e.target.checked })}
            />
            CPU illimité
          </label>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={form.unlimited_ram}
              onChange={(e) => setForm({ ...form, unlimited_ram: e.target.checked })}
            />
            RAM illimitée
          </label>
          <p className="sm:col-span-2 lg:col-span-4 text-[11px] text-cp-muted">
            Appliqué via cgroups v2 / slices systemd (Pulse) — pas de noyau propriétaire.
          </p>
        </div>

        <div className="border-y border-cp-border bg-cp-canvas/60 px-4 py-2 text-xs font-bold uppercase tracking-wide text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          Compteurs
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
          {(
            [
              ["domains", "Domaines"],
              ["emails", "E-mails"],
              ["databases", "Bases"],
              ["ftp_accounts", "FTP"],
              ["python_apps", "Apps Python"],
              ["node_apps", "Apps Node.js"],
              ["docker_containers", "Conteneurs Docker"],
            ] as const
          ).map(([key, label]) => (
            <Field key={key} label={label}>
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                value={form[key]}
                onChange={setNum(key)}
              />
            </Field>
          ))}
          {form.package_type === "reseller" && (
            <Field label="Comptes clients max (0 = illimité)" className="sm:col-span-2">
              <input
                className="vz-input w-full"
                type="number"
                min={0}
                value={form.max_accounts}
                onChange={setNum("max_accounts")}
              />
              <p className="mt-1 text-[11px] text-cp-muted">
                {Number(form.max_accounts) === 0
                  ? "Illimité — le revendeur peut créer autant de comptes que nécessaire."
                  : `Limité à ${form.max_accounts} comptes clients.`}
              </p>
            </Field>
          )}
        </div>

        <div className="border-y border-cp-border bg-cp-canvas/60 px-4 py-2 text-xs font-bold uppercase tracking-wide text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          Options
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-2 p-4 text-sm">
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

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-cp-border bg-cp-canvas/40 px-4 py-3 dark:border-ink-800 dark:bg-ink-900/40">
          <Link to="/whm/packages" className="vz-btn-ghost text-sm">
            Annuler
          </Link>
          <button
            className="whm-btn-create min-w-[10rem]"
            type="submit"
            disabled={submitting}
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Enregistrement…
              </>
            ) : mode === "create" ? (
              <>
                <Package className="h-4 w-4" />
                Créer le package
              </>
            ) : (
              "Enregistrer"
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
