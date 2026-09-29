import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, SlidersHorizontal } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageChrome";

interface TweakSettingMeta {
  key: string;
  label: string;
  type: "bool" | "int" | "choice" | "str";
  default: boolean | number | string;
  help?: string;
  min?: number;
  max?: number;
  choices?: string[];
}

interface TweakCategory {
  id: string;
  label: string;
  settings: TweakSettingMeta[];
}

interface TweakPayload {
  categories: TweakCategory[];
  values: Record<string, boolean | number | string>;
}

export function TweakSettingsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [cat, setCat] = useState("security");
  const [values, setValues] = useState<Record<string, boolean | number | string>>({});
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["tweak-settings"],
    queryFn: () => apiRequest<TweakPayload>("/server-setup/tweak-settings/"),
  });

  useEffect(() => {
    if (data?.values) setValues({ ...data.values });
    if (data?.categories?.[0] && !data.categories.some((c) => c.id === cat)) {
      setCat(data.categories[0].id);
    }
  }, [data, cat]);

  const active = useMemo(
    () => data?.categories.find((c) => c.id === cat) || data?.categories?.[0],
    [data, cat],
  );

  const dirty = useMemo(() => {
    if (!data?.values) return false;
    return Object.keys(values).some((k) => values[k] !== data.values[k]);
  }, [values, data]);

  const save = useMutation({
    mutationFn: () =>
      apiRequest<TweakPayload>("/server-setup/tweak-settings/", {
        method: "PUT",
        body: JSON.stringify({ values }),
      }),
    onSuccess: (payload) => {
      setValues({ ...payload.values });
      setOkMsg("Tweak Settings enregistrés.");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["tweak-settings"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  function setKey(key: string, value: boolean | number | string) {
    setValues((prev) => ({ ...prev, [key]: value }));
    setOkMsg(null);
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={title}
        subtitle="Enable/disable features · Security · Email · DNS · PHP · Backups · UI · Performance"
        actions={
          <button
            type="button"
            className="vz-btn-primary inline-flex items-center gap-1.5 disabled:opacity-50"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate()}
          >
            <Save className="h-4 w-4" />
            {save.isPending ? "Enregistrement…" : "Save"}
          </button>
        }
      />

      {(error || okMsg) && (
        <div
          className={`rounded-lg border px-3 py-2 text-sm ${
            error
              ? "border-rose-200 bg-rose-50 text-rose-800"
              : "border-emerald-200 bg-emerald-50 text-emerald-800"
          }`}
        >
          {error || okMsg}
        </div>
      )}

      {isLoading || !data ? (
        <p className="text-sm text-cp-muted">Chargement…</p>
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row">
          <aside className="vz-panel w-full shrink-0 overflow-hidden lg:w-56">
            <p className="border-b border-cp-border/70 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-cp-muted">
              Catégories
            </p>
            <nav className="flex gap-1 overflow-x-auto p-1.5 lg:flex-col lg:overflow-visible">
              {data.categories.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setCat(c.id)}
                  className={`rounded-md px-2.5 py-1.5 text-left text-sm transition ${
                    active?.id === c.id
                      ? "bg-cp-navy text-white dark:bg-white/15"
                      : "text-cp-text hover:bg-cp-canvas dark:hover:bg-white/5"
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </nav>
          </aside>

          <div className="vz-panel min-w-0 flex-1 p-4">
            <div className="mb-4 flex items-center gap-2">
              <SlidersHorizontal className="h-4 w-4 text-cp-navy dark:text-white/70" />
              <h2 className="text-base font-semibold">{active?.label}</h2>
            </div>
            <div className="space-y-4">
              {(active?.settings || []).map((s) => (
                <div
                  key={s.key}
                  className="flex flex-col gap-2 border-b border-cp-border/50 pb-4 last:border-0 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 sm:max-w-[60%]">
                    <p className="text-sm font-medium">{s.label}</p>
                    {s.help && <p className="mt-0.5 text-xs text-cp-muted">{s.help}</p>}
                    <p className="mt-0.5 font-mono text-[10px] text-cp-muted/80">{s.key}</p>
                  </div>
                  <div className="shrink-0">
                    {s.type === "bool" ? (
                      <button
                        type="button"
                        role="switch"
                        aria-checked={Boolean(values[s.key])}
                        onClick={() => setKey(s.key, !values[s.key])}
                        className={`relative h-7 w-12 rounded-full transition ${
                          values[s.key] ? "bg-cp-navy" : "bg-slate-300 dark:bg-slate-600"
                        }`}
                      >
                        <span
                          className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition ${
                            values[s.key] ? "left-5" : "left-0.5"
                          }`}
                        />
                      </button>
                    ) : s.type === "choice" ? (
                      <select
                        className="vz-input min-w-[8rem]"
                        value={String(values[s.key] ?? s.default)}
                        onChange={(e) => setKey(s.key, e.target.value)}
                      >
                        {(s.choices || []).map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="number"
                        className="vz-input w-28 tabular-nums"
                        value={Number(values[s.key] ?? s.default)}
                        min={s.min}
                        max={s.max}
                        onChange={(e) => setKey(s.key, Number(e.target.value))}
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
