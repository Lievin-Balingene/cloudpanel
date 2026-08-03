import { FormEvent, useEffect, useId, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { Eye, EyeOff, Loader2, Server } from "lucide-react";
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
    <div className="flex min-h-screen items-center justify-center bg-cp-navy p-4">
      <div className="w-full max-w-md overflow-hidden rounded border border-black/20 bg-white shadow-lg animate-fade-up">
        <div className="bg-cp-orange px-6 py-5 text-white">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded bg-white/15">
              <Server className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-wide">V-zone Panel</h1>
              <p className="text-sm text-white/90">Connexion WHM / Compte client</p>
            </div>
          </div>
        </div>

        <form className="space-y-4 p-6" onSubmit={onSubmit} noValidate>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-cp-muted" htmlFor={`${idPrefix}-id`}>
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
            <label className="mb-1 block text-xs font-semibold uppercase text-cp-muted" htmlFor={`${idPrefix}-password`}>
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
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase text-cp-muted" htmlFor={`${idPrefix}-otp`}>
                Code 2FA
              </label>
              <input
                ref={otpRef}
                id={`${idPrefix}-otp`}
                className="vz-input tracking-[0.25em]"
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
            <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
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

          <p className="text-center text-xs text-cp-muted">
            Administrateurs / revendeurs → WHM · Clients → panneau d&apos;hébergement
          </p>
        </form>
      </div>
    </div>
  );
}
