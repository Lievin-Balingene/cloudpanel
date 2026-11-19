import { FormEvent, useId, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Eye, EyeOff, KeyRound, Loader2 } from "lucide-react";
import { ApiClientError, apiRequest } from "@/lib/api";
import { detectPortalSync } from "@/lib/portal";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = useMemo(() => (params.get("token") || "").trim(), [params]);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const portal = detectPortalSync();
  const isAdmin = portal === "admin";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!token) {
      setError("Lien invalide ou incomplet. Refaites une demande « mot de passe oublié ».");
      return;
    }
    if (password !== confirm) {
      setError("Les mots de passe ne correspondent pas.");
      return;
    }
    if (password.length < 10) {
      setError("Le nouveau mot de passe doit contenir au moins 10 caractères.");
      return;
    }
    setLoading(true);
    try {
      await apiRequest("/auth/forgot-password/confirm/", {
        method: "POST",
        body: JSON.stringify({
          token,
          code: code.trim(),
          new_password: password,
          confirm_password: confirm,
        }),
      });
      navigate("/login", { replace: true, state: { passwordReset: true } });
    } catch (err) {
      const apiErr = err instanceof ApiClientError ? err : null;
      setError(apiErr?.message ?? "Impossible de réinitialiser le mot de passe.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className={
        isAdmin
          ? "vz-login-bg-admin flex min-h-screen flex-col items-center justify-center px-4 py-12"
          : "vz-login-bg-client flex min-h-screen flex-col items-center justify-center px-4 py-12"
      }
    >
      <main
        className={
          isAdmin
            ? "w-full max-w-[420px] rounded border border-[#3d4f63] bg-[#f0f2f5] p-6 shadow-lg"
            : "w-full max-w-[420px] rounded border border-slate-200 bg-white p-6 shadow-sm"
        }
      >
        <div className="mb-4 flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-cp-orange" />
          <h1 className="text-lg font-semibold text-[#1a2f45]">Nouveau mot de passe</h1>
        </div>
        <p className="mb-4 text-sm text-slate-600">
          Saisissez le code reçu par e-mail, puis choisissez un nouveau mot de passe fort. Toutes
          les sessions existantes seront déconnectées.
        </p>

        {!token ? (
          <div className="space-y-3">
            <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              Lien incomplet. Demandez un nouvel e-mail de réinitialisation.
            </p>
            <Link to="/forgot-password" className="block text-center text-sm font-medium text-cp-orange-dark underline">
              Mot de passe oublié
            </Link>
          </div>
        ) : (
          <form className="space-y-3.5" onSubmit={onSubmit}>
            <div>
              <label className="mb-1 block text-[13px] text-slate-600" htmlFor={`${id}-code`}>
                Code e-mail (ex. ABCD-EFGH)
              </label>
              <input
                id={`${id}-code`}
                className="vz-input tracking-[0.15em]"
                type="text"
                required
                autoComplete="one-time-code"
                autoCapitalize="characters"
                spellCheck={false}
                maxLength={12}
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                disabled={loading}
                autoFocus
              />
            </div>
            <div>
              <label className="mb-1 block text-[13px] text-slate-600" htmlFor={`${id}-new`}>
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
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-slate-400 hover:text-slate-600"
                  onClick={() => setShow((v) => !v)}
                  aria-label={show ? "Masquer" : "Afficher"}
                >
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-[13px] text-slate-600" htmlFor={`${id}-cf`}>
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
                disabled={loading}
              />
            </div>
            {error && (
              <p role="alert" className="rounded border border-red-200 bg-red-50 px-2.5 py-2 text-[13px] text-red-700">
                {error}
              </p>
            )}
            <button
              type="submit"
              className={isAdmin ? "vz-btn-primary w-full py-2" : "whm-btn-create w-full py-2"}
              disabled={loading || !code.trim() || !password || !confirm}
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Enregistrement…
                </>
              ) : (
                "Réinitialiser le mot de passe"
              )}
            </button>
            <Link to="/login" className="block text-center text-xs text-slate-500 hover:underline">
              Retour à la connexion
            </Link>
          </form>
        )}
      </main>
    </div>
  );
}
