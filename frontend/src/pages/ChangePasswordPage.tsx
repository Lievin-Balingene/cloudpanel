import { FormEvent, useId, useState } from "react";
import { Navigate } from "react-router-dom";
import { Eye, EyeOff, KeyRound, Loader2 } from "lucide-react";
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
    <div className="login-stage relative flex min-h-screen items-center justify-center overflow-hidden px-6 py-12">
      <div className="login-aurora pointer-events-none absolute inset-0" aria-hidden />
      <div className="login-grid pointer-events-none absolute inset-0" aria-hidden />

      <div className="login-reveal relative z-10 w-full max-w-md">
        <p className="mb-6 text-center font-display text-4xl font-semibold text-white">V-zone</p>
        <form
          className="rounded-2xl border border-white/10 bg-[#0c1622]/78 p-6 shadow-[0_24px_80px_rgba(0,0,0,0.35)] backdrop-blur-xl sm:p-8"
          onSubmit={onSubmit}
        >
          <div className="mb-6 flex items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-400/15 text-emerald-300">
              <KeyRound className="h-5 w-5" />
            </div>
            <div>
              <h1 className="font-display text-xl font-semibold text-white">
                Changer le mot de passe
              </h1>
              <p className="mt-1 text-sm text-white/55">
                Obligatoire avant d’utiliser le panneau. Choisissez un mot de passe fort (≥ 10 caractères).
              </p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-white/80" htmlFor={`${id}-cur`}>
                Mot de passe actuel
              </label>
              <input
                id={`${id}-cur`}
                className="login-input"
                type={show ? "text" : "password"}
                required
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-white/80" htmlFor={`${id}-new`}>
                Nouveau mot de passe
              </label>
              <div className="relative">
                <input
                  id={`${id}-new`}
                  className="login-input pr-11"
                  type={show ? "text" : "password"}
                  required
                  minLength={10}
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-white/50 hover:text-white"
                  onClick={() => setShow((v) => !v)}
                  aria-label={show ? "Masquer" : "Afficher"}
                >
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-white/80" htmlFor={`${id}-cf`}>
                Confirmer
              </label>
              <input
                id={`${id}-cf`}
                className="login-input"
                type={show ? "text" : "password"}
                required
                minLength={10}
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>

            {error && (
              <p role="alert" className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2.5 text-sm text-rose-100">
                {error}
              </p>
            )}

            <button
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-400 px-4 py-3 text-sm font-semibold text-[#062016] transition hover:bg-emerald-300 disabled:opacity-60"
              type="submit"
              disabled={loading}
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Enregistrement…
                </>
              ) : (
                "Enregistrer et continuer"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
