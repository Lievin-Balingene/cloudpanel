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
    <div className="login-stage relative flex min-h-screen items-stretch overflow-hidden">
      <div className="login-aurora pointer-events-none absolute inset-0" aria-hidden />
      <div className="login-grid pointer-events-none absolute inset-0" aria-hidden />

      <div className="relative z-10 mx-auto flex w-full max-w-6xl flex-col justify-center gap-10 px-6 py-12 lg:flex-row lg:items-center lg:gap-20 lg:px-10">
        <header className="login-reveal max-w-xl text-left lg:flex-1">
          <p className="font-display text-4xl font-semibold tracking-tight text-white sm:text-5xl lg:text-6xl">
            V-zone
          </p>
          <h1 className="mt-4 max-w-md font-display text-2xl font-medium leading-snug text-white/95 sm:text-3xl">
            Infrastructure cloud, panneau unique.
          </h1>
          <p className="mt-4 max-w-sm text-base leading-relaxed text-white/65">
            Accédez à WHM ou à votre espace client avec le même compte sécurisé.
          </p>
        </header>

        <section
          className="login-reveal login-reveal-delay w-full max-w-md lg:flex-none"
          style={{ animationDelay: "120ms" }}
        >
          <form
            className="rounded-2xl border border-white/10 bg-[#0c1622]/78 p-6 shadow-[0_24px_80px_rgba(0,0,0,0.35)] backdrop-blur-xl sm:p-8"
            onSubmit={onSubmit}
            noValidate
          >
            <div className="mb-6 flex items-center gap-2 text-sm text-emerald-300/90">
              <ShieldCheck className="h-4 w-4 shrink-0" aria-hidden />
              <span>Connexion chiffrée · session protégée</span>
            </div>

            <div className="space-y-4">
              <div>
                <label
                  className="mb-1.5 block text-sm font-medium text-white/80"
                  htmlFor={`${idPrefix}-id`}
                >
                  E-mail ou identifiant
                </label>
                <input
                  ref={identifierRef}
                  id={`${idPrefix}-id`}
                  className="login-input"
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
                <label
                  className="mb-1.5 block text-sm font-medium text-white/80"
                  htmlFor={`${idPrefix}-password`}
                >
                  Mot de passe
                </label>
                <div className="relative">
                  <input
                    id={`${idPrefix}-password`}
                    className="login-input pr-11"
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
                    className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-white/50 transition hover:text-white"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {needsOtp && (
                <div className="login-reveal">
                  <label
                    className="mb-1.5 block text-sm font-medium text-white/80"
                    htmlFor={`${idPrefix}-otp`}
                  >
                    Code d’authentification (2FA)
                  </label>
                  <input
                    ref={otpRef}
                    id={`${idPrefix}-otp`}
                    className="login-input tracking-[0.35em]"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="000000"
                    maxLength={8}
                    value={otp}
                    onChange={(e) => setOtp(e.target.value.replace(/\s/g, ""))}
                    disabled={loading}
                  />
                  <p className="mt-1.5 text-xs text-white/45">
                    Ouvrez votre application d’authentification et saisissez le code à 6 chiffres.
                  </p>
                </div>
              )}

              {error && (
                <p
                  role="alert"
                  className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2.5 text-sm text-rose-100"
                >
                  {error}
                </p>
              )}

              <button
                className="group relative mt-2 flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-emerald-400 px-4 py-3 text-sm font-semibold text-[#062016] transition hover:bg-emerald-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
                type="submit"
                disabled={loading || !email.trim() || !password}
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    Connexion…
                  </>
                ) : needsOtp ? (
                  "Valider le code 2FA"
                ) : (
                  "Se connecter"
                )}
              </button>
            </div>

            <p className="mt-6 text-center text-xs leading-relaxed text-white/40">
              Admin / revendeur → WHM · Client → panneau d’hébergement
            </p>
          </form>
        </section>
      </div>
    </div>
  );
}
