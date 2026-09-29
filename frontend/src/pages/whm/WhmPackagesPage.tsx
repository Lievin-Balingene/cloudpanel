import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Package, Pencil, Plus, Power, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { EmptyState, PageHeader } from "@/components/ui/PageChrome";
import { useAuthStore } from "@/stores/auth";
import type { HostingPackage } from "@/types";

export function WhmPackagesPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const me = useAuthStore((s) => s.user);
  const isAdmin = me?.role === "administrator";
  const { data: packages = [], isLoading } = useQuery({
    queryKey: ["packages"],
    queryFn: () => apiRequest<HostingPackage[]>("/packages/"),
  });

  const [tab, setTab] = useState<"client" | "reseller">("client");
  const effectiveTab = isAdmin ? tab : "client";
  const [error, setError] = useState<string | null>(null);

  const visiblePackages = packages.filter((p) => p.package_type === effectiveTab);

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["packages"] });

  const seed = useMutation({
    mutationFn: () => apiRequest("/packages/seed/", { method: "POST", body: "{}" }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Échec du seed."),
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
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Suppression impossible."),
  });

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title="Packages"
        subtitle="Plans client et revendeur. Créez ou modifiez un package sur une page dédiée."
        stats={[
          { label: "Client", value: packages.filter((p) => p.package_type === "client").length },
          {
            label: "Revendeur",
            value: packages.filter((p) => p.package_type === "reseller").length,
          },
        ]}
        actions={
          <div className="flex flex-wrap gap-2">
            <button
              className="vz-btn-ghost text-xs"
              type="button"
              onClick={() => seed.mutate()}
              disabled={seed.isPending}
            >
              Charger packages système
            </button>
            <Link
              to={`/whm/packages/create?type=${effectiveTab}`}
              className="vz-btn-primary inline-flex items-center gap-1.5 text-sm"
            >
              <Plus className="h-4 w-4" />
              Créer un package
            </Link>
          </div>
        }
      />

      {isAdmin && (
        <div className="flex gap-1 rounded-lg border border-cp-border bg-white p-1 shadow-sm dark:border-ink-800 dark:bg-ink-950">
          {(
            [
              ["client", "Client packages"],
              ["reseller", "Reseller packages"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition ${
                tab === id
                  ? "bg-cp-navy text-white shadow"
                  : "text-cp-muted hover:bg-cp-canvas hover:text-cp-navy dark:hover:bg-white/5"
              }`}
            >
              {label}
              <span className="ml-2 text-xs opacity-80">
                ({packages.filter((p) => p.package_type === id).length})
              </span>
            </button>
          ))}
        </div>
      )}

      {!isAdmin && (
        <p className="rounded border border-cp-border bg-[#f7fafc] px-3 py-2 text-xs text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          Packages <strong className="text-cp-navy dark:text-white">client</strong> uniquement —
          vous ne pouvez pas créer de package revendeur.
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger"
        >
          {error}
        </p>
      )}

      <div className="vz-panel overflow-x-auto">
        {isLoading ? (
          <p className="px-4 py-6 text-sm text-cp-muted">Chargement…</p>
        ) : visiblePackages.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Package className="h-8 w-8" />}
              message={
                effectiveTab === "reseller"
                  ? "Aucun package revendeur."
                  : "Aucun package client."
              }
              action={
                <Link
                  to={`/whm/packages/create?type=${effectiveTab}`}
                  className="vz-btn-primary inline-flex items-center gap-1.5"
                >
                  <Plus className="h-4 w-4" />
                  Créer un package
                </Link>
              }
            />
          </div>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
              <tr>
                <th className="px-3 py-2">Package</th>
                <th className="px-3 py-2">Disque</th>
                <th className="px-3 py-2">BP</th>
                <th className="px-3 py-2">Dom.</th>
                <th className="px-3 py-2">Mail</th>
                <th className="px-3 py-2">BDD</th>
                <th className="px-3 py-2">FTP</th>
                <th className="px-3 py-2">Py/Node</th>
                {effectiveTab === "reseller" && (
                  <th className="px-3 py-2">Max comptes</th>
                )}
                <th className="px-3 py-2">Assignés</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visiblePackages.map((pkg) => (
                <tr
                  key={pkg.id}
                  className="border-t border-cp-border dark:border-ink-800"
                >
                  <td className="px-3 py-2.5 font-medium">
                    <Link
                      to={`/whm/packages/${pkg.id}/edit`}
                      className="text-cp-navy hover:underline dark:text-white"
                    >
                      {pkg.name}
                    </Link>
                    {!pkg.is_active && (
                      <span className="ml-2 text-[10px] uppercase text-cp-muted">off</span>
                    )}
                    {pkg.is_default && (
                      <span className="ml-2 rounded bg-cp-orange-soft px-1.5 text-[10px] text-cp-orange-dark">
                        défaut
                      </span>
                    )}
                  </td>
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
                  {effectiveTab === "reseller" && (
                    <td className="px-3 py-2">
                      {pkg.max_accounts === 0 ? "∞" : pkg.max_accounts}
                    </td>
                  )}
                  <td className="px-3 py-2">{pkg.assigned_count ?? 0}</td>
                  <td className="px-3 py-2">
                    <div className="flex justify-end gap-1">
                      <IconAction
                        label="Modifier"
                        onClick={() => navigate(`/whm/packages/${pkg.id}/edit`)}
                      >
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
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
