import { LoginFormFields } from "./LoginFormFields";

type Props = { onBack?: () => void };

/** Login Admin — style WHM : fond sombre, carte centrée, peu de texte. */
export function AdminLoginView({ onBack }: Props) {
  return (
    <div className="vz-login-bg-admin flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="mb-6 flex items-center gap-3">
        <img src="/vzone-mark.svg" alt="" className="h-10 w-10 rounded-lg" width={40} height={40} />
        <span className="text-2xl font-semibold tracking-tight text-white">
          V-zone <span className="font-normal text-[#8eb8e0]">WHM</span>
        </span>
      </div>

      <main className="w-full max-w-[360px] rounded border border-[#3d4f63] bg-[#f0f2f5] p-6 shadow-lg">
        <LoginFormFields variant="admin" idHint="Username" passwordHint="Password" submitLabel="Log in" />
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

      <p className="mt-8 text-xs text-slate-500">Copyright © {new Date().getFullYear()} V-zone</p>
    </div>
  );
}
