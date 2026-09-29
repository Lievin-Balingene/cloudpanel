import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LockKeyhole, ShieldCheck, ShieldOff, User } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { PageHeader, StatusDot } from "@/components/ui/PageChrome";

interface PrivacyStatus {
  path: string;
  enabled: boolean;
  users: string[];
}

export function DirectoryPrivacyManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [path, setPath] = useState("public_html");
  const [lookupPath, setLookupPath] = useState("public_html");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const queryKey = ["directory-privacy", lookupPath];
  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: () =>
      apiRequest<PrivacyStatus>(
        `/files/directory-privacy/?path=${encodeURIComponent(lookupPath)}`,
      ),
  });

  const enable = useMutation({
    mutationFn: () =>
      apiRequest<PrivacyStatus>("/files/directory-privacy/", {
        method: "POST",
        body: JSON.stringify({ path, username, password }),
      }),
    onSuccess: (status) => {
      setLookupPath(status.path);
      setPassword("");
      setUsername("");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["directory-privacy"] });
    },
    onError: (err: Error) => setError(err.message),
  });
  const disable = useMutation({
    mutationFn: () =>
      apiRequest<PrivacyStatus>(
        `/files/directory-privacy/?path=${encodeURIComponent(lookupPath)}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey });
    },
    onError: (err: Error) => setError(err.message),
  });

  function inspect(e: FormEvent) {
    e.preventDefault();
    setLookupPath(path.trim());
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    enable.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Protégez un dossier web par identifiant et mot de passe."
        stats={[
          { label: "État", value: data?.enabled ? "Protégé" : "Public" },
          { label: "Utilisateurs", value: data?.users.length ?? 0 },
        ]}
      />
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950">
          {error}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <form onSubmit={inspect} className="vz-panel space-y-4 p-4 sm:p-5">
          <div className="flex items-center gap-2">
            <LockKeyhole className="h-4 w-4 text-cp-orange" />
            <h2 className="text-sm font-semibold text-cp-text">Dossier à protéger</h2>
          </div>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-cp-muted">Chemin relatif</span>
            <input
              className="vz-input w-full font-mono"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="public_html/espace-prive"
              required
            />
          </label>
          <button className="vz-btn-ghost" disabled={isLoading}>
            Vérifier le dossier
          </button>
        </form>
        <div className="vz-panel space-y-4 p-4 sm:p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-cp-text">État actuel</h2>
            <StatusDot
              status={data?.enabled ? "active" : "inactive"}
              label={data?.enabled ? "Protection active" : "Non protégé"}
            />
          </div>
          <p className="break-all font-mono text-sm text-cp-muted">/{data?.path ?? lookupPath}</p>
          {data?.users.length ? (
            <div className="space-y-2">
              {data.users.map((name) => (
                <div key={name} className="flex items-center gap-2 rounded-lg bg-cp-canvas px-3 py-2 text-sm dark:bg-ink-900">
                  <User className="h-4 w-4 text-cp-muted" />
                  {name}
                </div>
              ))}
            </div>
          ) : null}
          {data?.enabled && (
            <button
              type="button"
              className="vz-btn-ghost text-rose-600 hover:text-rose-700"
              disabled={disable.isPending}
              onClick={() => {
                if (window.confirm(`Désactiver la protection de /${lookupPath} ?`)) disable.mutate();
              }}
            >
              <ShieldOff className="h-4 w-4" />
              Désactiver la protection
            </button>
          )}
        </div>
      </div>
      <form onSubmit={submit} className="vz-panel space-y-4 p-4 sm:p-5">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-cp-orange" />
          <h2 className="text-sm font-semibold text-cp-text">Ajouter ou mettre à jour un accès</h2>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-cp-muted">Nom d’utilisateur</span>
            <input className="vz-input w-full" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-cp-muted">Mot de passe</span>
            <input type="password" minLength={8} className="vz-input w-full" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
        </div>
        <button className="vz-btn-primary" disabled={enable.isPending}>
          {enable.isPending ? "Activation…" : "Activer la protection"}
        </button>
      </form>
    </div>
  );
}
