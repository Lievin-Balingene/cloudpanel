import { LoginFormFields } from "./LoginFormFields";

type Props = { onBack?: () => void };

/** Login Client — style cPanel : fond gris, carte blanche, accent orange. */
export function ClientLoginView({ onBack }: Props) {
  return (
    <div className="vz-login-bg-client flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="mb-6 flex items-center gap-2.5">
        <img src="/vzone-mark.svg" alt="" className="h-11 w-11 rounded-lg" width={44} height={44} />
        <span className="text-[1.75rem] font-semibold tracking-tight text-[#1a2f45]">
          V-<span className="text-[#ff6c2c]">zone</span>
        </span>
      </div>

      <main className="w-full max-w-[360px] rounded border border-slate-200 bg-white p-6 shadow-sm">
        <LoginFormFields variant="client" idHint="Username" passwordHint="Password" submitLabel="Log in" />
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="mt-4 w-full text-center text-xs text-slate-500 hover:underline"
          >
            Back
          </button>
        )}
      </main>

      <p className="mt-8 text-xs text-slate-400">Copyright © {new Date().getFullYear()} V-zone</p>
    </div>
  );
}
