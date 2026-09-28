import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, ShieldCheck, Lock } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

interface SecurityMe {
  two_factor_enabled: boolean;
  must_change_password: boolean;
  force_2fa_admins: boolean;
  password_min_length: number;
  require_uppercase: boolean;
  require_digit: boolean;
  require_special: boolean;
}

interface TwoFactorSetup {
  otpauth_uri: string;
  secret: string;
  two_factor_enabled: boolean;
}

export function ClientSecurityPage() {
  const qc = useQueryClient();
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const { data: status } = useQuery({
    queryKey: ["security-me"],
    queryFn: () => apiRequest<SecurityMe>("/security/me/"),
  });
  const { data: twoFa } = useQuery({
    queryKey: ["auth-2fa"],
    queryFn: () => apiRequest<TwoFactorSetup>("/auth/2fa/"),
  });

  const [otp, setOtp] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const enable2fa = useMutation({
    mutationFn: () =>
      apiRequest("/auth/2fa/", { method: "POST", body: JSON.stringify({ otp }) }),
    onSuccess: async () => {
      setMessage("Double authentification activée.");
      setError(null);
      setOtp("");
      await qc.invalidateQueries({ queryKey: ["security-me"] });
      await qc.invalidateQueries({ queryKey: ["auth-2fa"] });
      await fetchMe();
    },
    onError: (err: Error) => setError(err.message),
  });

  const disable2fa = useMutation({
    mutationFn: () =>
      apiRequest("/auth/2fa/", { method: "DELETE", body: JSON.stringify({ otp }) }),
    onSuccess: async () => {
      setMessage("Double authentification désactivée.");
      setError(null);
      setOtp("");
      await qc.invalidateQueries({ queryKey: ["security-me"] });
      await qc.invalidateQueries({ queryKey: ["auth-2fa"] });
      await fetchMe();
    },
    onError: (err: Error) => setError(err.message),
  });

  const changePassword = useMutation({
    mutationFn: () =>
      apiRequest("/auth/password/", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      }),
    onSuccess: async () => {
      setMessage("Mot de passe mis à jour.");
      setError(null);
      setCurrentPassword("");
      setNewPassword("");
      await qc.invalidateQueries({ queryKey: ["security-me"] });
      await fetchMe();
    },
    onError: (err: Error) => setError(err.message),
  });

  function onEnable(e: FormEvent) {
    e.preventDefault();
    enable2fa.mutate();
  }

  function onDisable(e: FormEvent) {
    e.preventDefault();
    disable2fa.mutate();
  }

  function onPassword(e: FormEvent) {
    e.preventDefault();
    changePassword.mutate();
  }

  const twoFaOn = Boolean(status?.two_factor_enabled);

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel overflow-hidden">
        <div className="bg-gradient-to-r from-[#1e3a5f] to-[#2a4a6b] px-4 py-5 text-white sm:px-5">
          <div className="flex items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/15">
              <ShieldCheck className="h-5 w-5" />
            </span>
            <div>
              <h1 className="text-xl font-semibold">Sécurité du compte</h1>
              <p className="mt-1 text-sm text-white/80">
                Protégez votre accès avec un mot de passe solide et la double authentification.
              </p>
              {status?.must_change_password ? (
                <p className="mt-2 rounded-lg bg-amber-400/20 px-2.5 py-1.5 text-xs text-amber-50">
                  Un changement de mot de passe est requis.
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      {message && (
        <div className="rounded-xl border border-emerald-300 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
          {message}
        </div>
      )}
      {error && (
        <div className="rounded-xl border border-red-300 bg-red-50 px-3 py-2.5 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          {error}
        </div>
      )}

      <div className="vz-panel space-y-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-cp-orange" />
            <h2 className="text-sm font-semibold text-cp-text">Double authentification</h2>
          </div>
          <span
            className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              twoFaOn
                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
                : "bg-cp-canvas text-cp-muted dark:bg-ink-900"
            }`}
          >
            {twoFaOn ? "Activée" : "Désactivée"}
          </span>
        </div>

        {!twoFaOn && twoFa && (
          <>
            <p className="text-sm text-cp-muted">
              Ajoutez une couche de sécurité : ouvrez Google Authenticator, Authy ou une app
              similaire, puis saisissez le code à 6 chiffres.
            </p>
            <div className="rounded-xl border border-cp-border bg-cp-canvas/70 p-3 dark:border-ink-700 dark:bg-ink-900/60">
              <p className="text-xs font-medium text-cp-muted">Clé secrète à saisir dans l’app</p>
              <code className="mt-1 block break-all font-mono text-sm font-semibold tracking-wide text-cp-text">
                {twoFa.secret}
              </code>
            </div>
            <form onSubmit={onEnable} className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="block flex-1 text-sm">
                <span className="mb-1 block font-medium text-cp-muted">Code à 6 chiffres</span>
                <input
                  className="vz-input"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value)}
                  required
                />
              </label>
              <button
                type="submit"
                className="vz-btn-primary min-h-10"
                disabled={enable2fa.isPending}
              >
                Activer
              </button>
            </form>
          </>
        )}

        {twoFaOn && (
          <form onSubmit={onDisable} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="block flex-1 text-sm">
              <span className="mb-1 block font-medium text-cp-muted">
                Code pour désactiver
              </span>
              <input
                className="vz-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                required
              />
            </label>
            <button
              type="submit"
              className="vz-btn-ghost min-h-10"
              disabled={disable2fa.isPending}
            >
              Désactiver
            </button>
          </form>
        )}
      </div>

      <form onSubmit={onPassword} className="vz-panel space-y-4 p-4 sm:p-5">
        <div className="flex items-center gap-2">
          <Lock className="h-4 w-4 text-cp-orange" />
          <h2 className="text-sm font-semibold text-cp-text">Changer le mot de passe</h2>
        </div>
        <p className="text-xs text-cp-muted">
          Minimum {status?.password_min_length ?? 10} caractères
          {status?.require_digit ? " · au moins un chiffre" : ""}
          {status?.require_uppercase ? " · une majuscule" : ""}
          {status?.require_special ? " · un caractère spécial" : ""}.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-cp-muted">Mot de passe actuel</span>
            <input
              type="password"
              className="vz-input"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-cp-muted">Nouveau mot de passe</span>
            <input
              type="password"
              className="vz-input"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
          </label>
        </div>
        <button
          type="submit"
          className="vz-btn-primary min-h-10"
          disabled={changePassword.isPending}
        >
          Enregistrer le nouveau mot de passe
        </button>
      </form>
    </div>
  );
}
