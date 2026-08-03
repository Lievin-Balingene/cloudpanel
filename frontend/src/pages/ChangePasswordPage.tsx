import { FormEvent, useId, useState } from "react";
import { Navigate } from "react-router-dom";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { ApiClientError, apiRequest } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

export function ChangePasswordPage() {
  const user = useAuthStore((s) => s.user);
  const token = useAuthStore((s) => s.accessToken);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const id = useId();

  if (!token) return <Navigate to="/login" replace />;
  if (user && !user.must_change_password) {
    return <Navigate to={user.role === "client" ? "/panel" : "/whm"} replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirm) {
      setError("Les mots de passe ne correspondent pas.");
      return;
    }
    if (newPassword.length < 10) {
      setError("Le nouveau mot de passe doit contenir au moins 10 caractères.");
      return;
    }
    setLoading(true);
    try {
      await apiRequest("/auth/password/", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      await fetchMe();
    } catch (err) {
      const apiErr = err instanceof ApiClientError ? err : null;
      setError(apiErr?.message ?? "Impossible de changer le mot de passe.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="vz-login-bg relative flex min-h-screen items-center justify-center overflow-hidden p-5">
      <div className="vz-login-grid pointer-events-none absolute inset-0" aria-hidden />
      <div className="relative z-10 w-full max-w-[420px] animate-fade-up rounded-2xl border border-white/10 bg-white p-7 shadow-login sm:p-9">
        <p className="font-display text-2xl font-semibold text-cp-navy">V-zone</p>
        <h1 className="mt-4 font-display text-xl font-semibold text-cp-navy">Nouveau mot de passe</h1>
        <p className="mt-1 text-sm text-cp-muted">Obligatoire avant d&apos;accéder au panneau</p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-cp-muted" htmlFor={`${id}-cur`}>
              Mot de passe actuel
            </label>
            <input
              id={`${id}-cur`}
              className="vz-input"
              type={show ? "text" : "password"}
              required
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-cp-muted" htmlFor={`${id}-new`}>
              Nouveau mot de passe
            </label>
            <div className="relative">
              <input
                id={`${id}-new`}
                className="vz-input pr-10"
                type={show ? "text" : "password"}
                required
                minLength={10}
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              <button
                type="button"
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-cp-muted hover:text-cp-text"
                onClick={() => setShow((v) => !v)}
                aria-label={show ? "Masquer" : "Afficher"}
              >
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-cp-muted" htmlFor={`${id}-cf`}>
              Confirmer
            </label>
            <input
              id={`${id}-cf`}
              className="vz-input"
              type={show ? "text" : "password"}
              required
              minLength={10}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>

          {error && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
              {error}
            </p>
          )}

          <button className="vz-btn-primary w-full py-2.5" type="submit" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Enregistrement…
              </>
            ) : (
              "Enregistrer et continuer"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
