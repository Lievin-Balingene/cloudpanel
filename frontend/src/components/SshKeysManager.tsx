import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fingerprint, KeyRound, Plus, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader } from "@/components/ui/PageChrome";

interface SshKey {
  id: number;
  name: string;
  key_type: string;
  fingerprint: string;
}

export function SshKeysManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [publicKey, setPublicKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { data: keys = [], isLoading } = useQuery({
    queryKey: ["ssh-keys"],
    queryFn: () => apiRequest<SshKey[]>("/security/ssh-keys/"),
  });
  const create = useMutation({
    mutationFn: () =>
      apiRequest("/security/ssh-keys/", {
        method: "POST",
        body: JSON.stringify({ name, public_key: publicKey }),
      }),
    onSuccess: () => {
      setName("");
      setPublicKey("");
      setOpen(false);
      setError(null);
      void qc.invalidateQueries({ queryKey: ["ssh-keys"] });
    },
    onError: (err: Error) => setError(err.message),
  });
  const remove = useMutation({
    mutationFn: (id: number) => apiRequest(`/security/ssh-keys/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["ssh-keys"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Autorisez des clés publiques pour accéder à votre compte en SSH sans mot de passe."
        stats={[{ label: "Clés autorisées", value: keys.length }]}
        actions={
          <button type="button" className="vz-btn-primary" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" />
            Ajouter une clé
          </button>
        }
      />
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950">
          {error}
        </div>
      )}
      <div className="vz-panel overflow-hidden">
        {isLoading ? (
          <p className="px-4 py-10 text-center text-sm text-cp-muted">Chargement…</p>
        ) : keys.length === 0 ? (
          <EmptyState
            icon={<KeyRound className="h-5 w-5" />}
            message="Aucune clé SSH autorisée."
            action={
              <button type="button" className="vz-btn-primary" onClick={() => setOpen(true)}>
                <Plus className="h-4 w-4" />
                Ajouter une clé
              </button>
            }
          />
        ) : (
          <ul className="divide-y divide-cp-border dark:divide-ink-800">
            {keys.map((key) => (
              <li key={`${key.id}-${key.fingerprint}`} className="flex items-center justify-between gap-3 px-4 py-3.5">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold text-cp-text">{key.name || "Clé sans commentaire"}</p>
                    <span className="rounded-md bg-cp-canvas px-2 py-0.5 text-[11px] text-cp-muted dark:bg-ink-900">
                      {key.key_type}
                    </span>
                  </div>
                  <p className="mt-1 flex items-center gap-1.5 break-all font-mono text-xs text-cp-muted">
                    <Fingerprint className="h-3.5 w-3.5 shrink-0" />
                    {key.fingerprint}
                  </p>
                </div>
                <IconAction
                  label={`Supprimer ${key.name || key.fingerprint}`}
                  danger
                  onClick={() => {
                    if (window.confirm("Supprimer cette clé SSH ?")) remove.mutate(key.id);
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </IconAction>
              </li>
            ))}
          </ul>
        )}
      </div>
      {open && (
        <Modal title="Ajouter une clé SSH" onClose={() => setOpen(false)} wide>
          <form onSubmit={submit} className="space-y-3">
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-cp-text">Nom ou commentaire</span>
              <input className="vz-input w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ordinateur portable" />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-cp-text">Clé publique</span>
              <textarea className="vz-input min-h-32 w-full font-mono text-xs" value={publicKey} onChange={(e) => setPublicKey(e.target.value)} placeholder="ssh-ed25519 AAAA…" required />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setOpen(false)}>Annuler</button>
              <button className="vz-btn-primary" disabled={create.isPending}>
                {create.isPending ? "Ajout…" : "Ajouter"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
