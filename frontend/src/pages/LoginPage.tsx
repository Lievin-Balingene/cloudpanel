import { FormEvent, useEffect, useId, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { Eye, EyeOff, Loader2, ShieldCheck } from "lucide-react";
import { ApiClientError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

export function LoginPage() {
  const token = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const login = useAuthStore((s) => s.login);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [needsOtp, setNeedsOtp] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const idPrefix = useId();
  const identifierRef = useRef<HTMLInputElement>(null);
  const otpRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (needsOtp) otpRef.current?.focus();
    else identifierRef.current?.focus();
  }, [needsOtp]);

  if (token && user) {
    if (user.must_change_password) {
      return <Navigate to="/change-password" replace />;
    }
    return <Navigate to={user.role === "client" ? "/panel" : "/whm"} replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email.trim(), password, otp || undefined);
    } catch (err) {
      const apiErr = err instanceof ApiClientError ? err : null;
      const message = apiErr?.message ?? "Connexion impossible.";
      const code = apiErr?.payload?.error?.code ?? "";
      if (code === "requires_2fa" || code === "invalid_otp" || message.toLowerCase().includes("2fa")) {
        setNeedsOtp(true);
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="vz-login-bg relative flex min-h-screen items-stretch overflow-hidden">
      <div className="vz-login-grid pointer-events-none absolute inset-0" aria-hidden />

      {/* Brand panel */}
      <aside className="relative z-10 hidden w-[46%] flex-col justify-between p-10 text-white lg:flex xl:p-14">
        <div className="animate-fade-in">
          <div className="flex items-center gap-3">
            <img
              src="/vzone-mark.svg"
              alt="V-zone"
              className="h-12 w-12 rounded-xl shadow-md"
              width={48}
              height={48}
            />
            <div>
              <p className="font-display text-4xl font-semibold tracking-tight xl:text-5xl">V-zone</p>
              <p className="mt-1 text-sm font-medium uppercase tracking-[0.22em] text-white/55">Panel</p>
            </div>
          </div>
        </div>
        <div className="max-w-md animate-fade-up" style={{ animationDelay: "80ms" }}>
          <h1 className="font-display text-3xl font-medium leading-tight text-white/95 xl:text-4xl">
            Hébergement maîtrisé, panneau clair.
          </h1>
          <p className="mt-4 text-base leading-relaxed text-white/65">
            Admin pour les opérateurs, espace client pour vos sites — fichiers, e-mail, bases et apps au même endroit.
          </p>
        </div>
        <p className="text-xs text-white/40 animate-fade-in" style={{ animationDelay: "160ms" }}>
          Accès sécurisé · 2FA disponible
        </p>
      </aside>

      {/* Form */}
      <main className="relative z-10 flex flex-1 items-center justify-center p-5 sm:p-8">
        <div className="w-full max-w-[420px] animate-fade-up rounded-2xl border border-white/10 bg-white p-7 shadow-login sm:p-9">
          <div className="mb-7 flex items-center gap-2.5 lg:hidden">
            <img src="/vzone-mark.svg" alt="V-zone" className="h-9 w-9 rounded-lg" width={36} height={36} />
            <div>
              <p className="font-display text-2xl font-semibold text-cp-navy">V-zone</p>
              <p className="text-xs font-medium uppercase tracking-[0.2em] text-cp-muted">Panel</p>
            </div>
          </div>

          <div className="mb-6">
            <h2 className="font-display text-xl font-semibold text-cp-navy">Connexion</h2>
            <p className="mt-1 text-sm text-cp-muted">Admin ou compte d&apos;hébergement</p>
          </div>

          <form className="space-y-4" onSubmit={onSubmit} noValidate>
            <div>
              <label className="mb-1.5 block text-xs font-semibold text-cp-muted" htmlFor={`${idPrefix}-id`}>
                E-mail ou identifiant
              </label>
              <input
                ref={identifierRef}
                id={`${idPrefix}-id`}
                className="vz-input"
                type="text"
                name="username"
                required
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                placeholder="admin ou vous@domaine.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-semibold text-cp-muted" htmlFor={`${idPrefix}-password`}>
                Mot de passe
              </label>
              <div className="relative">
                <input
                  id={`${idPrefix}-password`}
                  className="vz-input pr-10"
                  type={showPassword ? "text" : "password"}
                  name="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-cp-muted hover:text-cp-text"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {needsOtp && (
              <div className="animate-fade-up rounded-lg border border-cp-link-soft bg-cp-link-soft/50 p-3">
                <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-cp-navy" htmlFor={`${idPrefix}-otp`}>
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Code 2FA
                </label>
                <input
                  ref={otpRef}
                  id={`${idPrefix}-otp`}
                  className="vz-input tracking-[0.28em]"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  maxLength={8}
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\s/g, ""))}
                  disabled={loading}
                />
              </div>
            )}

            {error && (
              <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
                {error}
              </p>
            )}

            <button
              className="vz-btn-primary w-full py-2.5"
              type="submit"
              disabled={loading || !email.trim() || !password}
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Connexion…
                </>
              ) : needsOtp ? (
                "Valider le code 2FA"
              ) : (
                "Se connecter"
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-[11px] leading-relaxed text-cp-muted">
            Administrateurs &amp; revendeurs → WHM
            <br />
            Clients → panneau d&apos;hébergement
          </p>
        </div>
      </main>
    </div>
  );
}
