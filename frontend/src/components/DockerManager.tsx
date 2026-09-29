import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Box,
  FileText,
  Hammer,
  Layers,
  Package,
  Play,
  Plus,
  RefreshCw,
  Square,
  Trash2,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot } from "@/components/ui/PageChrome";

type DockerTab = "containers" | "images" | "build" | "compose";

interface DockerOverview {
  containers: number;
  running: number;
  stopped: number;
  error: number;
  builds?: number;
  builds_running?: number;
  compose_projects?: number;
  compose_running?: number;
  images?: number;
  image_prefix?: string;
  provision_mode: string;
  docker_available?: boolean;
  docker_hint?: string;
}

interface DockerContainerItem {
  id: number;
  name: string;
  image: string;
  tag: string;
  image_ref: string;
  status: string;
  ports: Record<string, string>;
  memory_mb: number;
  container_id: string;
  last_error: string;
}

interface DockerImageItem {
  repository: string;
  tag: string;
  id: string;
  size: string;
  created: string;
  owned: boolean;
}

interface DockerBuildJob {
  id: number;
  name: string;
  context_path: string;
  dockerfile: string;
  image_name: string;
  tag: string;
  built_image_ref: string;
  status: string;
  progress: number;
  log: string;
  last_error: string;
}

interface DockerComposeProject {
  id: number;
  name: string;
  project_path: string;
  compose_file: string;
  status: string;
  log: string;
  last_error: string;
  last_deployed_at: string | null;
}

function publicHttpUrl(hostPort: string): string {
  const host = typeof window !== "undefined" ? window.location.hostname : "127.0.0.1";
  return `http://${host}:${hostPort}/`;
}

function splitImageRef(ref: string): { image: string; tag: string } {
  const idx = ref.lastIndexOf(":");
  if (idx <= 0) return { image: ref, tag: "latest" };
  return { image: ref.slice(0, idx), tag: ref.slice(idx + 1) };
}

const TAB_LABELS: { id: DockerTab; label: string; icon: typeof Box }[] = [
  { id: "containers", label: "Conteneurs", icon: Box },
  { id: "images", label: "Images", icon: Package },
  { id: "build", label: "Build", icon: Hammer },
  { id: "compose", label: "Compose", icon: Layers },
];

export function DockerManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<DockerTab>("containers");
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string | null>(null);
  const [logTitle, setLogTitle] = useState("Journaux");

  const { data: overview } = useQuery({
    queryKey: ["docker-overview"],
    queryFn: () => apiRequest<DockerOverview>("/docker/overview/"),
  });

  const dockerBlocked = overview?.provision_mode !== "mock" && overview?.docker_available === false;

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["docker-overview"] });
    void qc.invalidateQueries({ queryKey: ["docker-containers"] });
    void qc.invalidateQueries({ queryKey: ["docker-images"] });
    void qc.invalidateQueries({ queryKey: ["docker-builds"] });
    void qc.invalidateQueries({ queryKey: ["docker-compose"] });
  };

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Panel Docker complet : conteneurs, images, build Dockerfile et Compose."
        stats={[
          { label: "Conteneurs", value: overview?.containers ?? "—" },
          { label: "Images", value: overview?.images ?? "—" },
          { label: "Builds", value: overview?.builds ?? "—" },
          { label: "Compose", value: overview?.compose_projects ?? "—" },
        ]}
      />

      {dockerBlocked && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
          {overview?.docker_hint ||
            "Docker indisponible — sudo bash /opt/vzone/scripts/ensure-docker-access.sh"}
        </p>
      )}

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger dark:border-red-900 dark:bg-red-950/30">
          {error}
        </p>
      )}

      <div className="flex flex-wrap gap-1 border-b border-cp-border pb-1 dark:border-ink-800">
        {TAB_LABELS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={`inline-flex items-center gap-1.5 rounded-t-lg px-3 py-2 text-sm font-medium transition ${
              tab === id
                ? "border border-b-0 border-cp-border bg-white text-cp-navy dark:border-ink-700 dark:bg-ink-900 dark:text-white"
                : "text-cp-muted hover:text-cp-navy dark:hover:text-white"
            }`}
            onClick={() => setTab(id)}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {tab === "containers" && (
        <ContainersTab
          dockerBlocked={dockerBlocked}
          onError={setError}
          onLogs={(t, l) => {
            setLogTitle(t);
            setLogs(l);
          }}
          invalidate={invalidateAll}
        />
      )}
      {tab === "images" && (
        <ImagesTab
          dockerBlocked={dockerBlocked}
          imagePrefix={overview?.image_prefix}
          onError={setError}
          invalidate={invalidateAll}
        />
      )}
      {tab === "build" && (
        <BuildTab
          dockerBlocked={dockerBlocked}
          imagePrefix={overview?.image_prefix}
          onError={setError}
          onLogs={(t, l) => {
            setLogTitle(t);
            setLogs(l);
          }}
          invalidate={invalidateAll}
        />
      )}
      {tab === "compose" && (
        <ComposeTab
          dockerBlocked={dockerBlocked}
          onError={setError}
          onLogs={(t, l) => {
            setLogTitle(t);
            setLogs(l);
          }}
          invalidate={invalidateAll}
        />
      )}

      {logs !== null && (
        <Modal title={logTitle} onClose={() => setLogs(null)}>
          <pre className="max-h-[60vh] overflow-auto rounded-lg bg-ink-950 p-3 text-xs text-ink-100 whitespace-pre-wrap">
            {logs || "(vide)"}
          </pre>
        </Modal>
      )}
    </div>
  );
}

/* ─── Conteneurs ─── */

function ContainersTab({
  dockerBlocked,
  onError,
  onLogs,
  invalidate,
}: {
  dockerBlocked: boolean;
  onError: (m: string | null) => void;
  onLogs: (title: string, log: string) => void;
  invalidate: () => void;
}) {
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    name: "",
    image: "nginx",
    tag: "alpine",
    host_port: "",
    container_port: "80",
    memory_mb: 512,
    volume: "public_html:/usr/share/nginx/html",
  });

  const { data: containers = [], isLoading } = useQuery({
    queryKey: ["docker-containers"],
    queryFn: () => apiRequest<DockerContainerItem[]>("/docker/containers/"),
  });

  const create = useMutation({
    mutationFn: () =>
      runWithProgress(`Docker · ${form.name}`, () =>
        apiRequest("/docker/containers/", {
          method: "POST",
          body: JSON.stringify({
            name: form.name,
            image: form.image,
            tag: form.tag,
            memory_mb: form.memory_mb,
            ports: form.host_port.trim() ? { [form.host_port.trim()]: form.container_port || "80" } : {},
            volumes: form.volume.trim() ? [form.volume.trim()] : [],
            start_now: true,
          }),
        }),
      ),
    onSuccess: () => {
      setCreateOpen(false);
      onError(null);
      invalidate();
    },
    onError: (e: Error) => onError(e.message),
  });

  const action = useMutation({
    mutationFn: ({ id, op, name }: { id: number; op: string; name: string }) =>
      runWithProgress(`Docker ${op} · ${name}`, () =>
        apiRequest(`/docker/containers/${id}/${op}/`, { method: "POST", body: "{}" }),
      ),
    onSuccess: invalidate,
    onError: (e: Error) => onError(e.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiRequest(`/docker/containers/${id}/`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const loadLogs = useMutation({
    mutationFn: (id: number) => apiRequest<{ logs: string }>(`/docker/containers/${id}/logs/?tail=200`),
    onSuccess: (d, id) => {
      const c = containers.find((x) => x.id === id);
      onLogs(`Logs · ${c?.name ?? id}`, d.logs);
    },
    onError: (e: Error) => onError(e.message),
  });

  return (
    <>
      <div className="flex justify-end">
        <button type="button" className="vz-btn-primary" disabled={dockerBlocked} onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" /> Nouveau conteneur
        </button>
      </div>
      <div className="vz-panel overflow-hidden">
        {isLoading ? (
          <p className="px-4 py-8 text-sm text-cp-muted">Chargement…</p>
        ) : containers.length === 0 ? (
          <EmptyState icon={<Box className="h-8 w-8" />} message="Aucun conteneur." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
                <tr>
                  <th className="px-4 py-2.5">Nom</th>
                  <th className="px-4 py-2.5">Image</th>
                  <th className="px-4 py-2.5">Ports / URL</th>
                  <th className="px-4 py-2.5">État</th>
                  <th className="px-4 py-2.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {containers.map((c) => (
                  <tr key={c.id} className="border-t border-cp-border/80 dark:border-ink-800">
                    <td className="px-4 py-3 font-medium">{c.name}</td>
                    <td className="px-4 py-3 font-mono text-xs">{c.image_ref}</td>
                    <td className="px-4 py-3 text-xs">
                      {Object.entries(c.ports || {}).map(([h, ct]) => (
                        <div key={h}>
                          {h}→{ct}{" "}
                          {c.status === "running" && (
                            <a href={publicHttpUrl(h)} target="_blank" rel="noopener noreferrer" className="text-sky-600 hover:underline">
                              http://…:{h}
                            </a>
                          )}
                        </div>
                      ))}
                    </td>
                    <td className="px-4 py-3"><StatusDot status={c.status} /></td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-0.5">
                        {c.status !== "running" ? (
                          <IconAction label="Start" disabled={dockerBlocked} onClick={() => action.mutate({ id: c.id, op: "start", name: c.name })}>
                            <Play className="h-4 w-4" />
                          </IconAction>
                        ) : (
                          <IconAction label="Stop" onClick={() => action.mutate({ id: c.id, op: "stop", name: c.name })}>
                            <Square className="h-4 w-4" />
                          </IconAction>
                        )}
                        <IconAction label="Logs" onClick={() => loadLogs.mutate(c.id)}><FileText className="h-4 w-4" /></IconAction>
                        <IconAction label="Delete" danger onClick={() => window.confirm(`Supprimer ${c.name} ?`) && remove.mutate(c.id)}>
                          <Trash2 className="h-4 w-4" />
                        </IconAction>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {createOpen && (
        <Modal title="Nouveau conteneur" onClose={() => setCreateOpen(false)}>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <input className="vz-input" placeholder="Nom" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <div className="grid grid-cols-2 gap-2">
              <input className="vz-input" placeholder="Image" required value={form.image} onChange={(e) => setForm({ ...form, image: e.target.value })} />
              <input className="vz-input" placeholder="Tag" value={form.tag} onChange={(e) => setForm({ ...form, tag: e.target.value })} />
            </div>
            <input className="vz-input font-mono text-xs" placeholder="Volume ex. app:/app" value={form.volume} onChange={(e) => setForm({ ...form, volume: e.target.value })} />
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setCreateOpen(false)}>Annuler</button>
              <button type="submit" className="vz-btn-primary" disabled={create.isPending}>Créer</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

/* ─── Images ─── */

function ImagesTab({
  dockerBlocked,
  imagePrefix,
  onError,
  invalidate,
}: {
  dockerBlocked: boolean;
  imagePrefix?: string;
  onError: (m: string | null) => void;
  invalidate: () => void;
}) {
  const [pullImage, setPullImage] = useState("nginx");
  const [pullTag, setPullTag] = useState("alpine");

  const { data: images = [], isLoading, refetch } = useQuery({
    queryKey: ["docker-images"],
    queryFn: () => apiRequest<DockerImageItem[]>("/docker/images/"),
  });

  const pull = useMutation({
    mutationFn: () =>
      runWithProgress(`Pull ${pullImage}:${pullTag}`, () =>
        apiRequest("/docker/images/pull/", { method: "POST", body: JSON.stringify({ image: pullImage, tag: pullTag }) }),
      ),
    onSuccess: () => { onError(null); invalidate(); },
    onError: (e: Error) => onError(e.message),
  });

  const removeImg = useMutation({
    mutationFn: ({ repository, tag }: { repository: string; tag: string }) =>
      apiRequest("/docker/images/remove/", { method: "POST", body: JSON.stringify({ repository, tag }) }),
    onSuccess: invalidate,
    onError: (e: Error) => onError(e.message),
  });

  return (
    <>
      <p className="text-sm text-cp-muted">
        Vos images buildées sont préfixées <code className="text-xs">{imagePrefix ?? "vz_…"}_</code>.
        Accès public en <strong>http://</strong> sur le port hôte (pas https).
      </p>
      <div className="vz-panel p-4">
        <h3 className="mb-2 text-sm font-semibold">Pull depuis Docker Hub</h3>
        <div className="flex flex-wrap gap-2">
          <input className="vz-input max-w-xs" value={pullImage} onChange={(e) => setPullImage(e.target.value)} placeholder="nginx" />
          <input className="vz-input w-24" value={pullTag} onChange={(e) => setPullTag(e.target.value)} placeholder="tag" />
          <button type="button" className="vz-btn-primary" disabled={dockerBlocked || pull.isPending} onClick={() => pull.mutate()}>
            Pull
          </button>
          <button type="button" className="vz-btn-ghost" onClick={() => refetch()}><RefreshCw className="h-4 w-4" /></button>
        </div>
      </div>
      <div className="vz-panel overflow-hidden">
        {isLoading ? (
          <p className="px-4 py-8 text-sm text-cp-muted">Chargement…</p>
        ) : images.length === 0 ? (
          <EmptyState icon={<Package className="h-8 w-8" />} message="Aucune image locale." />
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
              <tr>
                <th className="px-4 py-2.5">Repository</th>
                <th className="px-4 py-2.5">Tag</th>
                <th className="px-4 py-2.5">Taille</th>
                <th className="px-4 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {images.map((img) => (
                <tr key={`${img.repository}:${img.tag}`} className="border-t border-cp-border/80 dark:border-ink-800">
                  <td className="px-4 py-3 font-mono text-xs">{img.repository}</td>
                  <td className="px-4 py-3">{img.tag}</td>
                  <td className="px-4 py-3 text-cp-muted">{img.size}</td>
                  <td className="px-4 py-3 text-right">
                    {img.owned && (
                      <IconAction
                        label="Supprimer"
                        danger
                        onClick={() => window.confirm(`Supprimer ${img.repository}:${img.tag} ?`) && removeImg.mutate({ repository: img.repository, tag: img.tag })}
                      >
                        <Trash2 className="h-4 w-4" />
                      </IconAction>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

/* ─── Build ─── */

function BuildTab({
  dockerBlocked,
  imagePrefix,
  onError,
  onLogs,
  invalidate,
}: {
  dockerBlocked: boolean;
  imagePrefix?: string;
  onError: (m: string | null) => void;
  onLogs: (title: string, log: string) => void;
  invalidate: () => void;
}) {
  const [form, setForm] = useState({
    name: "",
    context_path: "app",
    dockerfile: "Dockerfile",
    image_name: "",
    tag: "latest",
    no_cache: false,
  });

  const { data: builds = [], isLoading } = useQuery({
    queryKey: ["docker-builds"],
    queryFn: () => apiRequest<DockerBuildJob[]>("/docker/builds/"),
    refetchInterval: (q) => {
      const d = q.state.data as DockerBuildJob[] | undefined;
      return d?.some((b) => b.status === "running" || b.status === "pending") ? 2000 : false;
    },
  });

  const startBuild = useMutation({
    mutationFn: () =>
      runWithProgress(`Build · ${form.name}`, () =>
        apiRequest("/docker/builds/", {
          method: "POST",
          body: JSON.stringify(form),
        }),
      ),
    onSuccess: () => { onError(null); invalidate(); },
    onError: (e: Error) => onError(e.message),
  });

  const template = useMutation({
    mutationFn: (kind: string) =>
      apiRequest("/docker/dockerfile-template/", {
        method: "POST",
        body: JSON.stringify({ context_path: form.context_path, kind }),
      }),
    onSuccess: () => onError(null),
    onError: (e: Error) => onError(e.message),
  });

  const runContainer = useMutation({
    mutationFn: (job: DockerBuildJob) => {
      const ref = job.built_image_ref || `${imagePrefix ?? "vz"}_${job.image_name}:${job.tag}`;
      const { image, tag } = splitImageRef(ref);
      return apiRequest("/docker/containers/", {
        method: "POST",
        body: JSON.stringify({ name: `${job.name}-run`, image, tag, start_now: true }),
      });
    },
    onSuccess: () => { onError(null); invalidate(); },
    onError: (e: Error) => onError(e.message),
  });

  return (
    <>
      <div className="rounded-lg border border-cp-border bg-cp-canvas/60 px-4 py-3 text-sm dark:border-ink-800">
        <p className="font-medium">Workflow build (style Portainer)</p>
        <ol className="mt-1 list-decimal pl-5 text-cp-muted">
          <li>Déposez votre code + Dockerfile dans Fichiers → <code>app/</code></li>
          <li>Lancez le build → image <code>{imagePrefix ?? "vz_user"}_nom:tag</code></li>
          <li>« Run » pour créer un conteneur depuis l’image buildée</li>
        </ol>
      </div>
      <div className="vz-panel p-4">
        <h3 className="mb-3 text-sm font-semibold">Nouveau build</h3>
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); startBuild.mutate(); }}>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="vz-input" placeholder="Nom du build" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="vz-input font-mono text-xs" placeholder="Dossier contexte (app)" required value={form.context_path} onChange={(e) => setForm({ ...form, context_path: e.target.value })} />
            <input className="vz-input font-mono text-xs" placeholder="Dockerfile" value={form.dockerfile} onChange={(e) => setForm({ ...form, dockerfile: e.target.value })} />
            <input className="vz-input" placeholder="Nom image (auto si vide)" value={form.image_name} onChange={(e) => setForm({ ...form, image_name: e.target.value })} />
            <input className="vz-input" placeholder="Tag" value={form.tag} onChange={(e) => setForm({ ...form, tag: e.target.value })} />
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="vz-btn-ghost text-xs" onClick={() => template.mutate("node")}>+ Dockerfile Node</button>
            <button type="button" className="vz-btn-ghost text-xs" onClick={() => template.mutate("nginx")}>+ Dockerfile nginx</button>
            <button type="button" className="vz-btn-ghost text-xs" onClick={() => template.mutate("python")}>+ Dockerfile Python</button>
            <button type="submit" className="vz-btn-primary ml-auto" disabled={dockerBlocked || startBuild.isPending}>Lancer le build</button>
          </div>
        </form>
      </div>
      <div className="vz-panel overflow-hidden">
        <div className="border-b border-cp-border px-4 py-2 dark:border-ink-800"><h3 className="text-sm font-semibold">Historique builds</h3></div>
        {isLoading ? (
          <p className="px-4 py-6 text-sm text-cp-muted">Chargement…</p>
        ) : builds.length === 0 ? (
          <EmptyState icon={<Hammer className="h-8 w-8" />} message="Aucun build." />
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
              <tr>
                <th className="px-4 py-2.5">Nom</th>
                <th className="px-4 py-2.5">Contexte</th>
                <th className="px-4 py-2.5">Image</th>
                <th className="px-4 py-2.5">État</th>
                <th className="px-4 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {builds.map((b) => (
                <tr key={b.id} className="border-t border-cp-border/80 dark:border-ink-800">
                  <td className="px-4 py-3">{b.name}</td>
                  <td className="px-4 py-3 font-mono text-xs">{b.context_path}/{b.dockerfile}</td>
                  <td className="px-4 py-3 font-mono text-xs">{b.built_image_ref || `${b.image_name}:${b.tag}`}</td>
                  <td className="px-4 py-3">
                    <StatusDot status={b.status} />
                    {b.status === "running" && <span className="ml-2 text-xs text-cp-muted">{b.progress}%</span>}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-1">
                      <IconAction label="Logs build" onClick={() => onLogs(`Build · ${b.name}`, b.log)}><FileText className="h-4 w-4" /></IconAction>
                      {b.status === "completed" && (
                        <IconAction label="Run conteneur" disabled={dockerBlocked} onClick={() => runContainer.mutate(b)}>
                          <Play className="h-4 w-4" />
                        </IconAction>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

/* ─── Compose ─── */

function ComposeTab({
  dockerBlocked,
  onError,
  onLogs,
  invalidate,
}: {
  dockerBlocked: boolean;
  onError: (m: string | null) => void;
  onLogs: (title: string, log: string) => void;
  invalidate: () => void;
}) {
  const [form, setForm] = useState({ name: "", project_path: "app", compose_file: "" });

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ["docker-compose"],
    queryFn: () => apiRequest<DockerComposeProject[]>("/docker/compose/"),
    refetchInterval: 3000,
  });

  const create = useMutation({
    mutationFn: () =>
      apiRequest("/docker/compose/", { method: "POST", body: JSON.stringify(form) }),
    onSuccess: () => { onError(null); invalidate(); },
    onError: (e: Error) => onError(e.message),
  });

  const composeAction = useMutation({
    mutationFn: ({ id, op }: { id: number; op: "up" | "down" }) =>
      runWithProgress(`Compose ${op}`, () =>
        apiRequest(`/docker/compose/${id}/${op}/`, { method: "POST", body: "{}" }),
      ),
    onSuccess: invalidate,
    onError: (e: Error) => onError(e.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => apiRequest(`/docker/compose/${id}/`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  return (
    <>
      <p className="text-sm text-cp-muted">
        Placez <code className="text-xs">docker-compose.yml</code> dans un dossier de votre home, enregistrez le projet, puis <strong>Up</strong> (build + démarrage).
      </p>
      <div className="vz-panel p-4">
        <h3 className="mb-2 text-sm font-semibold">Nouveau projet Compose</h3>
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <input className="vz-input" placeholder="Nom projet" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className="vz-input font-mono text-xs" placeholder="Dossier (app)" required value={form.project_path} onChange={(e) => setForm({ ...form, project_path: e.target.value })} />
          <input className="vz-input font-mono text-xs" placeholder="Fichier (auto)" value={form.compose_file} onChange={(e) => setForm({ ...form, compose_file: e.target.value })} />
          <button type="submit" className="vz-btn-primary" disabled={dockerBlocked}>Enregistrer</button>
        </form>
      </div>
      <div className="vz-panel overflow-hidden">
        {isLoading ? (
          <p className="px-4 py-6 text-sm text-cp-muted">Chargement…</p>
        ) : projects.length === 0 ? (
          <EmptyState icon={<Layers className="h-8 w-8" />} message="Aucun projet Compose." />
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
              <tr>
                <th className="px-4 py-2.5">Nom</th>
                <th className="px-4 py-2.5">Chemin</th>
                <th className="px-4 py-2.5">État</th>
                <th className="px-4 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id} className="border-t border-cp-border/80 dark:border-ink-800">
                  <td className="px-4 py-3">{p.name}</td>
                  <td className="px-4 py-3 font-mono text-xs">{p.project_path}/{p.compose_file}</td>
                  <td className="px-4 py-3"><StatusDot status={p.status} /></td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-1">
                      <IconAction label="Up" disabled={dockerBlocked} onClick={() => composeAction.mutate({ id: p.id, op: "up" })}><Play className="h-4 w-4" /></IconAction>
                      <IconAction label="Down" onClick={() => composeAction.mutate({ id: p.id, op: "down" })}><Square className="h-4 w-4" /></IconAction>
                      <IconAction label="Logs" onClick={() => onLogs(`Compose · ${p.name}`, p.log)}><FileText className="h-4 w-4" /></IconAction>
                      <IconAction label="Delete" danger onClick={() => window.confirm(`Supprimer ${p.name} ?`) && remove.mutate(p.id)}><Trash2 className="h-4 w-4" /></IconAction>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
