import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import {
  PackageFormPage,
  defaultPackageForm,
  type PackageForm,
} from "@/components/PackageFormPage";

export function WhmPackageCreatePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const me = useAuthStore((s) => s.user);
  const isAdmin = me?.role === "administrator";
  const [params] = useSearchParams();
  const typeParam = params.get("type");
  const initialType =
    isAdmin && typeParam === "reseller" ? "reseller" : "client";

  const initial = useMemo(() => defaultPackageForm(initialType), [initialType]);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: (form: PackageForm) =>
      apiRequest("/packages/", {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["packages"] });
      navigate("/whm/packages", { replace: true });
    },
    onError: (err: Error) => setError(err.message || "Création impossible."),
  });

  return (
    <PackageFormPage
      mode="create"
      initial={initial}
      allowResellerType={isAdmin}
      submitting={create.isPending}
      error={error}
      onSubmit={(form) => {
        setError(null);
        create.mutate(form);
      }}
    />
  );
}
