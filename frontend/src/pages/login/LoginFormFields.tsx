import { FormEvent, useEffect, useId, useRef, useState } from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { ApiClientError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

export type LoginFormVariant = "admin" | "client";

type LoginFormProps = {
  variant: LoginFormVariant;
  idHint?: string;
  passwordHint?: string;
  submitLabel?: string;
};

export function useLoginForm() {
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

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email.trim(), password, otp || undefined);
    } catch (err) {
      const apiErr = err instanceof ApiClientError ? err : null;
      const message = apiErr?.message ?? "Login failed.";
      const code = apiErr?.payload?.error?.code ?? "";
      if (code === "requires_2fa" || code === "invalid_otp" || message.toLowerCase().includes("2fa")) {
        setNeedsOtp(true);
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return {
    email,
    setEmail,
    password,
    setPassword,
    otp,
    setOtp,
    needsOtp,
    showPassword,
    setShowPassword,
    error,
    loading,
    idPrefix,
    identifierRef,
    otpRef,
    onSubmit,
  };
}

export function LoginFormFields({
  variant,
  idHint = "Username",
  passwordHint = "Password",
  submitLabel = "Log in",
}: LoginFormProps) {
  const form = useLoginForm();
  const isAdmin = variant === "admin";

  return (
    <form className="space-y-3.5" onSubmit={form.onSubmit} noValidate>
      <div>
        <label className="mb-1 block text-[13px] text-slate-600" htmlFor={`${form.idPrefix}-id`}>
          {idHint}
        </label>
        <input
          ref={form.identifierRef}
          id={`${form.idPrefix}-id`}
          className="vz-input"
          type="text"
          name="username"
          required
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          value={form.email}
          onChange={(e) => form.setEmail(e.target.value)}
          disabled={form.loading}
        />
      </div>

      <div>
        <label className="mb-1 block text-[13px] text-slate-600" htmlFor={`${form.idPrefix}-password`}>
          {passwordHint}
        </label>
        <div className="relative">
          <input
            id={`${form.idPrefix}-password`}
            className="vz-input pr-10"
            type={form.showPassword ? "text" : "password"}
            name="password"
            required
            autoComplete="current-password"
            value={form.password}
            onChange={(e) => form.setPassword(e.target.value)}
            disabled={form.loading}
          />
          <button
            type="button"
            className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-slate-400 hover:text-slate-600"
            onClick={() => form.setShowPassword((v) => !v)}
            aria-label={form.showPassword ? "Hide password" : "Show password"}
          >
            {form.showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {form.needsOtp && (
        <div>
          <label className="mb-1 block text-[13px] text-slate-600" htmlFor={`${form.idPrefix}-otp`}>
            Security Code
          </label>
          <input
            ref={form.otpRef}
            id={`${form.idPrefix}-otp`}
            className="vz-input tracking-[0.2em]"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={8}
            value={form.otp}
            onChange={(e) => form.setOtp(e.target.value.replace(/\s/g, ""))}
            disabled={form.loading}
          />
        </div>
      )}

      {form.error && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-2.5 py-2 text-[13px] text-red-700">
          {form.error}
        </p>
      )}

      <button
        className={
          isAdmin
            ? "vz-btn-primary mt-1 w-full py-2"
            : "whm-btn-create mt-1 w-full py-2"
        }
        type="submit"
        disabled={form.loading || !form.email.trim() || !form.password}
      >
        {form.loading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            …
          </>
        ) : form.needsOtp ? (
          "Verify"
        ) : (
          submitLabel
        )}
      </button>
    </form>
  );
}
