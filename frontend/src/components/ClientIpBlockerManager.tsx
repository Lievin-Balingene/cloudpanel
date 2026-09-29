import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Plus, Trash2 } from "lucide-react";
import { ApiClientError, apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { EmptyState, PageHeader } from "@/components/ui/PageChrome";

const BLOCK_FILE = "etc/ip_blocker.txt";

interface FileContent {
  content: string;
}

function parseLines(content: string) {
  return content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

async function readBlockList() {
  try {
    const file = await apiRequest<FileContent>(`/files/read/?path=${encodeURIComponent(BLOCK_FILE)}`);
    return parseLines(file.content);
  } catch (error) {
    if (error instanceof ApiClientError && error.status === 404) return [];
    throw error;
  }
}

async function ensureEtcDirectory() {
  try {
    await apiRequest("/files/?path=etc");
  } catch (error) {
    if (!(error instanceof ApiClientError) || error.status !== 404) throw error;
    await apiRequest("/files/mkdir/", {
      method: "POST",
      body: JSON.stringify({ path: "", name: "etc" }),
    });
  }
}

async function writeBlockList(lines: string[]) {
  await ensureEtcDirectory();
  return apiRequest("/files/write/", {
    method: "PUT",
    body: JSON.stringify({
      path: BLOCK_FILE,
      content: lines.length ? `${lines.join("\n")}\n` : "",
    }),
  });
}

export function ClientIpBlockerManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["client-ip-blocker"],
    queryFn: readBlockList,
  });
  const save = useMutation({
    mutationFn: writeBlockList,
    onSuccess: () => {
      setValue("");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["client-ip-blocker"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const address = value.trim();
    if (!address || /\s/.test(address) || (!address.includes(".") && !address.includes(":"))) {
      setError("Saisissez une adresse IP ou un réseau CIDR valide.");
      return;
    }
    if (entries.includes(address)) {
      setError("Cette adresse figure déjà dans la liste.");
      return;
    }
    save.mutate([...entries, address]);
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Ces adresses doivent être refusées au niveau web. La liste est stockée dans etc/ip_blocker.txt pour le panneau et une future synchronisation Nginx."
        stats={[{ label: "Adresses bloquées", value: entries.length }]}
      />
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950">
          {error}
        </div>
      )}
      <form onSubmit={submit} className="vz-panel flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
        <label className="block flex-1 text-sm">
          <span className="mb-1 block font-medium text-cp-muted">Adresse IP ou réseau CIDR</span>
          <input
            className="vz-input w-full font-mono"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="203.0.113.42 ou 203.0.113.0/24"
            required
          />
        </label>
        <button className="vz-btn-primary min-h-10" disabled={save.isPending}>
          <Plus className="h-4 w-4" />
          Ajouter
        </button>
      </form>
      <div className="vz-panel overflow-hidden">
        {isLoading ? (
          <p className="px-4 py-10 text-center text-sm text-cp-muted">Chargement…</p>
        ) : entries.length === 0 ? (
          <EmptyState icon={<Ban className="h-5 w-5" />} message="Aucune adresse IP n’est bloquée." />
        ) : (
          <ul className="divide-y divide-cp-border dark:divide-ink-800">
            {entries.map((entry, index) => (
              <li key={`${entry}-${index}`} className="flex items-center justify-between gap-3 px-4 py-3">
                <code className="text-sm font-semibold text-cp-text">{entry}</code>
                <IconAction
                  label={`Retirer ${entry}`}
                  danger
                  onClick={() => {
                    if (window.confirm(`Retirer ${entry} de la liste ?`)) {
                      save.mutate(entries.filter((_, itemIndex) => itemIndex !== index));
                    }
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </IconAction>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
