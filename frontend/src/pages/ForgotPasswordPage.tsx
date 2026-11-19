import { FormEvent, useId, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, Mail } from "lucide-react";
import { ApiClientError, apiRequest } from "@/lib/api";
import { detectPortalSync } from "@/lib/portal";

export function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const id = useId();
  const portal = detectPortalSync();
  const isAdmin = portal === "admin";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await apiRequest<{ detail: string }>("/auth/forgot-password/", {
        method: "POST",
        body: JSON.stringify({
          identifier: identifier.trim(),
          portal: portal === "client" ? "client" : "admin",
        }),
      });
      setDone(true);
    } catch (err) {
      const apiErr = err instanceof ApiClientError ? err : null;
      setError(apiErr?.message ?? "Impossible d’envoyer la demande.");
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
            ? "w-full max-w-[400px] rounded border border-[#3d4f63] bg-[#f0f2f5] p-6 shadow-lg"
            : "w-full max-w-[400px] rounded border border-slate-200 bg-white p-6 shadow-sm"
        }
      >
        <div className="mb-4 flex items-center gap-2">
          <Mail className="h-5 w-5 text-cp-orange" />
          <h1 className="text-lg font-semibold text-[#1a2f45]">Mot de passe oublié</h1>
        </div>
        <p className="mb-4 text-sm text-slate-600">
          Indiquez votre nom d’utilisateur ou e-mail. Si un compte existe, vous recevrez un lien
          sécurisé et un code de vérification (valables 20 minutes).
        </p>

        {done ? (
          <div className="space-y-4">
            <p className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
              Si un compte correspond, un e-mail avec un lien et un code a été envoyé. Vérifiez aussi
              vos indésirables.
            </p>
            <Link to="/login" className="block text-center text-sm font-medium text-cp-orange-dark underline">
              Retour à la connexion
            </Link>
          </div>
        ) : (
          <form className="space-y-3.5" onSubmit={onSubmit}>
            <div>
              <label className="mb-1 block text-[13px] text-slate-600" htmlFor={`${id}-id`}>
                Username or email
              </label>
              <input
                id={`${id}-id`}
                className="vz-input"
                type="text"
                required
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                disabled={loading}
                autoFocus
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
              disabled={loading || !identifier.trim()}
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Envoi…
                </>
              ) : (
                "Envoyer le lien et le code"
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
