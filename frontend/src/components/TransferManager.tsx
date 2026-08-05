import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft, RefreshCw, Server, Upload } from "lucide-react";
import { apiRequest, ApiClientError } from "@/lib/api";

type TransferOptions = {
  home: boolean;
  domains: boolean;
  dns: boolean;
  databases: boolean;
  email: boolean;
  ssl: boolean;
  ftp: boolean;
};

type TransferJob = {
  id: number;
  source_type: string;
  status: string;
  username: string;
  email: string;
  package_name: string;
  overwrite: boolean;
  archive_name: string;
  remote_host: string;
  remote_username: string;
  progress: number;
  current_step: string;
  log: string;
  result: Record<string, unknown>;
  last_error: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

type InspectData = {
  username: string;
  main_domain: string;
  contact_email: string;
  has_homedir: boolean;
  domains: { name: string; type: string; documentroot?: string }[];
  databases: { name: string; engine: string }[];
  mailboxes: number;
  has_dns: boolean;
  has_ssl: boolean;
  warnings: string[];
  archive_name?: string;
  temp_path?: string;
};

type RemoteAccount = {
  user: string;
  domain: string;
  email: string;
  plan: string;
  diskused: string;
  suspended: boolean;
};

const defaultOptions: TransferOptions = {
  home: true,
  domains: true,
  dns: true,
  databases: true,
  email: true,
  ssl: true,
  ftp: true,
};

export function TransferManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"archive" | "remote">("archive");
  const [file, setFile] = useState<File | null>(null);
  const [inspect, setInspect] = useState<InspectData | null>(null);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [packageName, setPackageName] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [options, setOptions] = useState<TransferOptions>(defaultOptions);
  const [error, setError] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);

  const [remoteHost, setRemoteHost] = useState("");
  const [remotePort, setRemotePort] = useState(2087);
  const [remoteSshPort, setRemoteSshPort] = useState(22);
  const [remoteUser, setRemoteUser] = useState("root");
  const [remoteToken, setRemoteToken] = useState("");
  const [insecureSsl, setInsecureSsl] = useState(true);
  const [remoteAccounts, setRemoteAccounts] = useState<RemoteAccount[]>([]);
  const [selectedRemote, setSelectedRemote] = useState("");
  const [remoteAuthInfo, setRemoteAuthInfo] = useState<string | null>(null);

  const { data: jobs } = useQuery({
    queryKey: ["transfer-jobs"],
    queryFn: () => apiRequest<TransferJob[]>("/transfer/jobs/"),
    refetchInterval: (query) => {
      const list = query.state.data;
      if (list?.some((j) => j.status === "pending" || j.status === "running")) return 2000;
      return false;
    },
  });

  const { data: activeJob } = useQuery({
    queryKey: ["transfer-job", activeJobId],
    queryFn: () => apiRequest<TransferJob>(`/transfer/jobs/${activeJobId}/`),
    enabled: !!activeJobId,
    refetchInterval: (q) => {
      const st = q.state.data?.status;
      if (st === "pending" || st === "running") return 1500;
      return false;
    },
  });

  useEffect(() => {
    if (activeJob && (activeJob.status === "completed" || activeJob.status === "failed")) {
      void qc.invalidateQueries({ queryKey: ["transfer-jobs"] });
    }
  }, [activeJob, qc]);

  const optionEntries = useMemo(
    () =>
      [
        ["home", "Fichiers (homedir)"],
        ["domains", "Domaines / docroots"],
        ["dns", "Zones DNS"],
        ["databases", "Bases MySQL"],
        ["email", "Comptes mail + Maildir"],
        ["ssl", "Certificats SSL"],
        ["ftp", "Comptes FTP"],
      ] as const,
    [],
  );

  const inspectMut = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Sélectionnez une archive cpmove/pkgacct.");
      const body = new FormData();
      body.append("file", file);
      return apiRequest<InspectData>("/transfer/archive/inspect/", { method: "POST", body });
    },
    onSuccess: (data) => {
      setError(null);
      setInspect(data);
      setUsername(data.username || "");
      setEmail(data.contact_email || "");
    },
    onError: (err: Error) => setError(err.message),
  });

  const startArchive = useMutation({
    mutationFn: async () => {
      if (!file && !inspect?.temp_path) throw new Error("Archive requise.");
      const body = new FormData();
      if (file) body.append("file", file);
      if (inspect?.temp_path) body.append("temp_path", inspect.temp_path);
      body.append("username", username);
      body.append("email", email);
      body.append("password", password);
      body.append("package_name", packageName);
      body.append("overwrite", overwrite ? "true" : "false");
      body.append("options", JSON.stringify(options));
      return apiRequest<TransferJob>("/transfer/archive/start/", { method: "POST", body });
    },
    onSuccess: (job) => {
      setError(null);
      setActiveJobId(job.id);
      void qc.invalidateQueries({ queryKey: ["transfer-jobs"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const listRemote = useMutation({
    mutationFn: () =>
      apiRequest<{ accounts: RemoteAccount[]; count: number; auth_method?: string }>(
        "/transfer/remote/list/",
        {
          method: "POST",
          body: JSON.stringify({
            host: remoteHost,
            port: remotePort,
            user: remoteUser,
            token: remoteToken,
            insecure_ssl: insecureSsl,
            ssh_port: remoteSshPort,
          }),
        },
      ),
    onSuccess: (data) => {
      setError(null);
      setRemoteAccounts(data.accounts || []);
      if (data.auth_method === "basic-password") {
        setRemoteAuthInfo(`Connecté via mot de passe (${data.count ?? 0} comptes)`);
      } else if (data.auth_method) {
        setRemoteAuthInfo(`Connecté via API Token/hash (${data.count ?? 0} comptes)`);
      } else {
        setRemoteAuthInfo(`${data.count ?? 0} comptes listés`);
      }
    },
    onError: (err: Error) => {
      setRemoteAuthInfo(null);
      setError(err.message);
    },
  });

  const startRemote = useMutation({
    mutationFn: () => {
      const remoteUserName = (selectedRemote || username).trim();
      if (!remoteUserName) throw new Error("Sélectionnez un compte dans la liste ou saisissez le username.");
      if (!remoteHost.trim() || !remoteToken.trim()) {
        throw new Error("Host WHM et token/mot de passe sont requis.");
      }
      return apiRequest<TransferJob>("/transfer/remote/start/", {
        method: "POST",
        body: JSON.stringify({
          host: remoteHost.trim(),
          port: remotePort,
          user: remoteUser,
          token: remoteToken.trim(),
          insecure_ssl: insecureSsl,
          ssh_port: remoteSshPort,
          remote_username: remoteUserName,
          username: username.trim() || remoteUserName,
          email,
          password,
          package_name: packageName,
          overwrite,
          options,
        }),
      });
    },
    onSuccess: (job) => {
      setError(null);
      setActiveJobId(job.id);
      void qc.invalidateQueries({ queryKey: ["transfer-jobs"] });
    },
    onError: (err: Error) => {
      const msg = err instanceof ApiClientError ? err.message : err.message;
      setError(msg);
    },
  });

  const canStartRemote =
    !startRemote.isPending &&
    !!remoteHost.trim() &&
    !!remoteToken.trim() &&
    !!(selectedRemote || username).trim();

  function onInspect(e: FormEvent) {
    e.preventDefault();
    inspectMut.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold flex items-center gap-2">
              <ArrowRightLeft className="h-5 w-5 text-cp-orange" />
              {title}
            </h1>
            <p className="mt-1 text-sm text-cp-muted max-w-3xl">
              Migrez des comptes cPanel/WHM vers V-zone sans perte de données. L’arborescence cible
              reste identique à cPanel (<code className="text-xs">public_html</code>,{" "}
              <code className="text-xs">mail/</code>, <code className="text-xs">ssl/</code>,{" "}
              <code className="text-xs">domains/</code>, etc.).
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className={tab === "archive" ? "vz-btn-primary" : "vz-btn-ghost"}
              onClick={() => setTab("archive")}
            >
              <Upload className="mr-1 inline h-4 w-4" />
              Archive cpmove
            </button>
            <button
              type="button"
              className={tab === "remote" ? "vz-btn-primary" : "vz-btn-ghost"}
              onClick={() => setTab("remote")}
            >
              <Server className="mr-1 inline h-4 w-4" />
              WHM distant
            </button>
          </div>
        </div>
      </div>

      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger whitespace-pre-wrap">
          {error}
        </p>
      )}

      {tab === "archive" && (
        <form className="vz-panel space-y-3 p-4" onSubmit={onInspect}>
          <h2 className="text-sm font-semibold uppercase text-cp-muted">1. Archive cPanel</h2>
          <p className="text-sm text-cp-muted">
            Formats supportés : <code className="text-xs">cpmove-USER.tar.gz</code>,{" "}
            <code className="text-xs">backup-USER-*.tar.gz</code>, sortie{" "}
            <code className="text-xs">/scripts/pkgacct</code>.
          </p>
          <input
            type="file"
            accept=".gz,.tgz,.tar,.zip"
            className="vz-input"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setInspect(null);
            }}
          />
          <button className="vz-btn-secondary" type="submit" disabled={inspectMut.isPending || !file}>
            {inspectMut.isPending ? "Analyse…" : "Analyser l’archive"}
          </button>

          {inspect && (
            <div className="rounded border border-cp-border bg-cp-canvas/40 p-3 text-sm space-y-1">
              <p>
                <strong>User</strong> {inspect.username} · <strong>Domaine</strong>{" "}
                {inspect.main_domain || "—"}
              </p>
              <p>
                Domaines: {inspect.domains.length} · Bases: {inspect.databases.length} · Boîtes:{" "}
                {inspect.mailboxes} · Homedir: {inspect.has_homedir ? "oui" : "non"} · DNS:{" "}
                {inspect.has_dns ? "oui" : "non"} · SSL: {inspect.has_ssl ? "oui" : "non"}
              </p>
              {inspect.warnings?.length > 0 && (
                <ul className="list-disc pl-5 text-amber-800">
                  {inspect.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </form>
      )}

      {tab === "remote" && (
        <div className="vz-panel space-y-3 p-4">
          <h2 className="text-sm font-semibold uppercase text-cp-muted">WHM distant</h2>
          <p className="text-sm text-cp-muted">
            Identifiant WHM : <strong>API Token</strong> ou <strong>mot de passe root</strong> (recommandé :
            permet le téléchargement SCP du cpmove). Le packaging utilise l&apos;API WHM ; le téléchargement
            passe par <strong>SSH/SFTP</strong> (port ci-dessous).
          </p>
          <div className="grid gap-2 md:grid-cols-2">
            <input
              className="vz-input"
              placeholder="hostname WHM"
              value={remoteHost}
              onChange={(e) => setRemoteHost(e.target.value)}
            />
            <input
              className="vz-input"
              type="number"
              placeholder="port WHM API (2087)"
              value={remotePort}
              onChange={(e) => setRemotePort(Number(e.target.value) || 2087)}
            />
            <input
              className="vz-input"
              type="number"
              placeholder="port SSH (22)"
              value={remoteSshPort}
              onChange={(e) => setRemoteSshPort(Number(e.target.value) || 22)}
            />
            <input
              className="vz-input"
              placeholder="utilisateur WHM (root)"
              value={remoteUser}
              onChange={(e) => setRemoteUser(e.target.value)}
            />
            <input
              className="vz-input md:col-span-2"
              type="password"
              placeholder="API Token ou mot de passe root WHM/SSH"
              value={remoteToken}
              onChange={(e) => setRemoteToken(e.target.value)}
              autoComplete="off"
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={insecureSsl} onChange={(e) => setInsecureSsl(e.target.checked)} />
            Accepter certificat SSL auto-signé
          </label>
          <button
            type="button"
            className="vz-btn-secondary"
            disabled={listRemote.isPending || !remoteHost || !remoteToken}
            onClick={() => listRemote.mutate()}
          >
            {listRemote.isPending ? "Connexion…" : "Lister les comptes"}
          </button>
          {remoteAuthInfo && !error && (
            <p className="text-sm text-emerald-700">{remoteAuthInfo}</p>
          )}
          {remoteAccounts.length > 0 && (
            <div className="max-h-64 overflow-auto rounded border border-cp-border">
              <table className="w-full text-left text-sm">
                <thead className="bg-cp-canvas text-xs uppercase text-cp-muted">
                  <tr>
                    <th className="px-2 py-1">User</th>
                    <th className="px-2 py-1">Domaine</th>
                    <th className="px-2 py-1">Plan</th>
                    <th className="px-2 py-1">Disque</th>
                  </tr>
                </thead>
                <tbody>
                  {remoteAccounts.map((a) => (
                    <tr
                      key={a.user}
                      className={`cursor-pointer border-t border-cp-border hover:bg-cp-orange/5 ${
                        selectedRemote === a.user ? "bg-cp-orange/10" : ""
                      }`}
                      onClick={() => {
                        setSelectedRemote(a.user);
                        setUsername(a.user);
                        setEmail(a.email || "");
                        if (a.plan) setPackageName(a.plan);
                      }}
                    >
                      <td className="px-2 py-1 font-medium">{a.user}</td>
                      <td className="px-2 py-1">{a.domain}</td>
                      <td className="px-2 py-1">{a.plan}</td>
                      <td className="px-2 py-1">{a.diskused}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {remoteAccounts.length > 0 && !selectedRemote && (
            <p className="text-xs text-amber-700">
              Cliquez une ligne du tableau pour sélectionner le compte à migrer (ou saisissez le
              username ci-dessous).
            </p>
          )}
        </div>
      )}

      <div className="vz-panel space-y-3 p-4">
        <h2 className="text-sm font-semibold uppercase text-cp-muted">2. Compte cible V-zone</h2>
        <div className="grid gap-2 md:grid-cols-2">
          <input
            className="vz-input"
            placeholder="username (identique cPanel)"
            value={username}
            onChange={(e) => {
              const v = e.target.value;
              setUsername(v);
              if (tab === "remote") {
                setSelectedRemote(v.trim());
              }
            }}
            required
          />
          <input
            className="vz-input"
            placeholder="email contact"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="vz-input"
            type="password"
            placeholder="mot de passe panel (optionnel, sinon généré)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <input
            className="vz-input"
            placeholder="package V-zone (optionnel)"
            value={packageName}
            onChange={(e) => setPackageName(e.target.value)}
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
          Écraser si le compte existe déjà
        </label>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {optionEntries.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={options[key]}
                onChange={(e) => setOptions((o) => ({ ...o, [key]: e.target.checked }))}
              />
              {label}
            </label>
          ))}
        </div>
        {tab === "archive" ? (
          <button
            type="button"
            className="vz-btn-primary"
            disabled={startArchive.isPending || !username || (!file && !inspect?.temp_path)}
            onClick={() => startArchive.mutate()}
          >
            {startArchive.isPending ? "Démarrage…" : "Lancer le transfert"}
          </button>
        ) : (
          <div className="space-y-2">
            {!canStartRemote && (
              <p className="text-xs text-amber-700">
                Pour activer le transfert : host WHM + token/mot de passe + compte (cliquez une ligne
                ou saisissez le username).
              </p>
            )}
            <button
              type="button"
              className="vz-btn-primary"
              disabled={!canStartRemote}
              onClick={() => startRemote.mutate()}
            >
              {startRemote.isPending ? "Transfert en cours…" : "Lancer le transfert distant"}
            </button>
          </div>
        )}
      </div>

      {(activeJob || (jobs && jobs[0])) && (
        <div className="vz-panel space-y-2 p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase text-cp-muted">Progression</h2>
            <button
              type="button"
              className="vz-btn-ghost"
              onClick={() => void qc.invalidateQueries({ queryKey: ["transfer-jobs"] })}
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
          {(() => {
            const job = activeJob || jobs?.[0];
            if (!job) return null;
            return (
              <div className="space-y-2 text-sm">
                <p>
                  Job #{job.id} · <strong>{job.username}</strong> · {job.status} · {job.progress}%
                </p>
                <div className="h-2 overflow-hidden rounded bg-cp-border">
                  <div className="h-full bg-cp-orange transition-all" style={{ width: `${job.progress}%` }} />
                </div>
                <p className="text-cp-muted">{job.current_step}</p>
                {job.last_error && <p className="text-cp-danger whitespace-pre-wrap">{job.last_error}</p>}
                {job.status === "completed" && job.result && (
                  <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-900">
                    <p className="font-medium">Transfert terminé</p>
                    <p>
                      Compte <code>{String(job.result.username)}</code>
                      {job.result.password ? (
                        <>
                          {" "}
                          — mot de passe temporaire : <code>{String(job.result.password)}</code>
                        </>
                      ) : null}
                    </p>
                    <p className="text-xs mt-1">
                      Les mots de passe mail/FTP/cPanel hashés non réversibles ont été régénérés ;
                      fichiers, bases, DNS et SSL sont conservés.
                    </p>
                  </div>
                )}
                {job.log && (
                  <pre className="max-h-56 overflow-auto rounded bg-ink-950 p-2 text-xs text-white/90">
                    {job.log}
                  </pre>
                )}
              </div>
            );
          })()}
        </div>
      )}

      {jobs && jobs.length > 0 && (
        <div className="vz-panel p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase text-cp-muted">Historique</h2>
          <ul className="divide-y divide-cp-border text-sm">
            {jobs.map((j) => (
              <li key={j.id} className="flex cursor-pointer items-center justify-between py-2 hover:bg-cp-canvas/50 px-1" onClick={() => setActiveJobId(j.id)}>
                <span>
                  #{j.id} {j.username} · {j.source_type} · {j.archive_name || j.remote_host || "—"}
                </span>
                <span className="text-cp-muted">
                  {j.status} · {j.progress}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
