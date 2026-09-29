import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import type { HostingPackage } from "@/types";
import {
  PackageFormPage,
  packageToForm,
  type PackageForm,
} from "@/components/PackageFormPage";

export function WhmPackageEditPage() {
  const { id } = useParams();
  const packageId = Number(id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const me = useAuthStore((s) => s.user);
  const isAdmin = me?.role === "administrator";
  const [error, setError] = useState<string | null>(null);

  const { data: packages = [], isLoading } = useQuery({
    queryKey: ["packages"],
    queryFn: () => apiRequest<HostingPackage[]>("/packages/"),
  });

  const pkg = packages.find((p) => p.id === packageId);
  const initial = useMemo(() => (pkg ? packageToForm(pkg) : null), [pkg]);

  const update = useMutation({
    mutationFn: (form: PackageForm) =>
      apiRequest(`/packages/${packageId}/`, {
        method: "PATCH",
        body: JSON.stringify(form),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["packages"] });
      navigate("/whm/packages", { replace: true });
    },
    onError: (err: Error) => setError(err.message || "Modification impossible."),
  });

  if (!Number.isFinite(packageId) || packageId <= 0) {
    return (
      <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
        Identifiant de package invalide.{" "}
        <Link className="underline" to="/whm/packages">
          Retour
        </Link>
      </p>
    );
  }

  if (isLoading || !initial) {
    return (
      <div className="vz-panel p-6 text-sm text-cp-muted">
        {isLoading ? "Chargement du package…" : "Package introuvable."}
        {!isLoading && (
          <div className="mt-3">
            <Link className="vz-btn-ghost text-sm" to="/whm/packages">
              Retour à la liste
            </Link>
          </div>
        )}
      </div>
    );
  }

  return (
    <PackageFormPage
      key={pkg?.id}
      mode="edit"
      initial={initial}
      allowResellerType={isAdmin}
      submitting={update.isPending}
      error={error}
      onSubmit={(form) => {
        setError(null);
        update.mutate(form);
      }}
    />
  );
}
