import { create } from "zustand";

export type OperationStatus = "running" | "success" | "error";

export type OperationItem = {
  id: string;
  title: string;
  detail?: string;
  /** 0–100, ou -1 = indéterminé (animé) */
  percent: number;
  status: OperationStatus;
  error?: string;
  startedAt: number;
};

type OperationsState = {
  items: OperationItem[];
  start: (input: { title: string; detail?: string; percent?: number }) => string;
  update: (id: string, patch: Partial<Pick<OperationItem, "detail" | "percent">>) => void;
  succeed: (id: string, detail?: string) => void;
  fail: (id: string, error: string) => void;
  dismiss: (id: string) => void;
  clearFinished: () => void;
};

function uid() {
  return `op_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export const useOperationsStore = create<OperationsState>((set, get) => ({
  items: [],
  start: ({ title, detail, percent = -1 }) => {
    const id = uid();
    set((s) => ({
      items: [
        {
          id,
          title,
          detail,
          percent,
          status: "running",
          startedAt: Date.now(),
        },
        ...s.items,
      ].slice(0, 8),
    }));
    return id;
  },
  update: (id, patch) => {
    set((s) => ({
      items: s.items.map((it) =>
        it.id === id && it.status === "running" ? { ...it, ...patch } : it,
      ),
    }));
  },
  succeed: (id, detail) => {
    set((s) => ({
      items: s.items.map((it) =>
        it.id === id
          ? { ...it, status: "success", percent: 100, detail: detail ?? it.detail, error: undefined }
          : it,
      ),
    }));
    window.setTimeout(() => get().dismiss(id), 2800);
  },
  fail: (id, error) => {
    set((s) => ({
      items: s.items.map((it) =>
        it.id === id ? { ...it, status: "error", percent: 100, error, detail: error } : it,
      ),
    }));
  },
  dismiss: (id) => set((s) => ({ items: s.items.filter((it) => it.id !== id) })),
  clearFinished: () =>
    set((s) => ({ items: s.items.filter((it) => it.status === "running") })),
}));

/** Exécute une promesse avec barre de progression (indéterminée → 100 %). */
export async function runWithProgress<T>(
  title: string,
  fn: () => Promise<T>,
  opts?: { detail?: string; tickDetail?: (elapsedMs: number) => string },
): Promise<T> {
  const store = useOperationsStore.getState();
  const id = store.start({ title, detail: opts?.detail, percent: -1 });
  const started = Date.now();
  let fake = 8;
  const timer = window.setInterval(() => {
    fake = Math.min(92, fake + Math.random() * 7 + 2);
    const elapsed = Date.now() - started;
    store.update(id, {
      percent: fake,
      detail: opts?.tickDetail?.(elapsed) ?? opts?.detail,
    });
  }, 450);

  try {
    const result = await fn();
    window.clearInterval(timer);
    store.succeed(id, opts?.detail ?? "Terminé");
    return result;
  } catch (err) {
    window.clearInterval(timer);
    const message = err instanceof Error ? err.message : "Échec de l'opération";
    store.fail(id, message);
    throw err;
  }
}
