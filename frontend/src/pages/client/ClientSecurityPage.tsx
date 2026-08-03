import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
      setMessage("2FA activée.");
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
      setMessage("2FA désactivée.");
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

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">Sécurité du compte</h1>
        <p className="text-sm text-cp-muted">
          Authentification à deux facteurs et changement de mot de passe.
          {status?.must_change_password ? " — changement de mot de passe requis." : ""}
        </p>
      </div>

      {message && (
        <div className="rounded border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
          {message}
        </div>
      )}
      {error && (
        <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          {error}
        </div>
      )}

      <div className="vz-panel space-y-3 p-4">
        <h2 className="text-sm font-semibold">
          2FA TOTP — {status?.two_factor_enabled ? "activée" : "désactivée"}
        </h2>
        {!status?.two_factor_enabled && twoFa && (
          <>
            <p className="text-sm text-cp-muted">
              Scannez l&apos;URI dans votre application authenticator, ou saisissez le secret :
            </p>
            <code className="block break-all rounded bg-cp-canvas p-2 text-xs dark:bg-ink-900">
              {twoFa.secret}
            </code>
            <p className="break-all text-xs text-cp-muted">{twoFa.otpauth_uri}</p>
            <form onSubmit={onEnable} className="flex flex-wrap items-end gap-3">
              <label className="text-sm">
                Code OTP
                <input
                  className="mt-1 block rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value)}
                  required
                />
              </label>
              <button type="submit" className="rounded bg-cp-orange px-3 py-2 text-sm font-medium text-white">
                Activer 2FA
              </button>
            </form>
          </>
        )}
        {status?.two_factor_enabled && (
          <form onSubmit={onDisable} className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              Code OTP pour désactiver
              <input
                className="mt-1 block rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                required
              />
            </label>
            <button type="submit" className="rounded border border-cp-border px-3 py-2 text-sm dark:border-ink-700">
              Désactiver 2FA
            </button>
          </form>
        )}
      </div>

      <form onSubmit={onPassword} className="vz-panel grid gap-3 p-4 md:grid-cols-2">
        <h2 className="md:col-span-2 text-sm font-semibold">Changer le mot de passe</h2>
        <p className="md:col-span-2 text-xs text-cp-muted">
          Min. {status?.password_min_length ?? 10} caractères
          {status?.require_digit ? ", chiffre requis" : ""}
          {status?.require_uppercase ? ", majuscule requise" : ""}
          {status?.require_special ? ", caractère spécial requis" : ""}.
        </p>
        <label className="text-sm">
          Mot de passe actuel
          <input
            type="password"
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
          />
        </label>
        <label className="text-sm">
          Nouveau mot de passe
          <input
            type="password"
            className="mt-1 w-full rounded border border-cp-border bg-transparent px-2 py-1.5 dark:border-ink-700"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
        </label>
        <div className="md:col-span-2">
          <button type="submit" className="rounded bg-cp-orange px-3 py-2 text-sm font-medium text-white">
            Mettre à jour
          </button>
        </div>
      </form>
    </div>
  );
}
