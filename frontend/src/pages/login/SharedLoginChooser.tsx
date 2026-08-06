type Props = {
  onChoose: (kind: "admin" | "client") => void;
};

/** Choix Admin / Client — deux boutons, sans texte superflu. */
export function SharedLoginChooser({ onChoose }: Props) {
  return (
    <div className="vz-login-bg flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <img
        src="/vzone-mark.svg"
        alt="V-zone"
        className="mb-5 h-12 w-12 rounded-xl"
        width={48}
        height={48}
      />
      <p className="mb-8 text-2xl font-semibold text-white">V-zone</p>

      <div className="flex w-full max-w-sm flex-col gap-3">
        <button
          type="button"
          onClick={() => onChoose("admin")}
          className="rounded border border-slate-600 bg-[#1a2f45] px-5 py-3.5 text-left text-white transition hover:border-[#7eb6e8]"
        >
          <span className="block text-sm font-semibold">WHM</span>
          <span className="text-xs text-slate-400">Administrator</span>
        </button>
        <button
          type="button"
          onClick={() => onChoose("client")}
          className="rounded border border-slate-200 bg-white px-5 py-3.5 text-left transition hover:border-[#ff6c2c]"
        >
          <span className="block text-sm font-semibold text-[#1a2f45]">
            V-<span className="text-[#ff6c2c]">zone</span>
          </span>
          <span className="text-xs text-slate-500">Hosting account</span>
        </button>
      </div>
    </div>
  );
}
