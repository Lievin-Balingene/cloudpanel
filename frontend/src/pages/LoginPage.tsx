import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { Server } from "lucide-react";
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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (token && user) {
    return <Navigate to={user.role === "client" ? "/panel" : "/whm"} replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email, password, otp || undefined);
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
      <div className="w-full max-w-md overflow-hidden rounded border border-black/20 bg-white shadow-lg">
        <div className="bg-cp-orange px-6 py-4 text-white">
          <div className="flex items-center gap-3">
            <Server className="h-7 w-7" />
            <div>
              <h1 className="text-lg font-semibold">V-zone Panel</h1>
              <p className="text-xs text-white/90">Connexion WHM / Compte client</p>
            </div>
          </div>
        </div>
        <form className="space-y-4 p-6" onSubmit={onSubmit}>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-cp-muted">E-mail</label>
            <input
              className="vz-input"
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-cp-muted">
              Mot de passe
            </label>
            <input
              className="vz-input"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {needsOtp && (
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase text-cp-muted">
                Code 2FA
              </label>
              <input
                className="vz-input"
                type="text"
                inputMode="numeric"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
              />
            </div>
          )}
          {error && (
            <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
              {error}
            </p>
          )}
          <button className="vz-btn-primary w-full" type="submit" disabled={loading}>
            {loading ? "Connexion…" : "Se connecter"}
          </button>
          <p className="text-center text-xs text-cp-muted">
            Les administrateurs / revendeurs ouvrent WHM · Les clients ouvrent le panneau.
          </p>
        </form>
      </div>
    </div>
  );
}
