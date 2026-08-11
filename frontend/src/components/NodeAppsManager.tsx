import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ExternalLink,
  FileText,
  FolderOpen,
  Globe2,
  Loader2,
  Package,
  Play,
  Plus,
  RefreshCw,
  Search,
  Square,
  Trash2,
  Download,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, Tabs } from "@/components/ui/PageChrome";

interface NodeOverview {
  apps: number;
  running: number;
  stopped: number;
  error: number;
  provision_mode: string;
  home_path?: string;
}

interface NodeAppItem {
  id: number;
  name: string;
  label: string;
  node_version: string;
  framework: string;
  relative_root: string;
  start_script: string;
  entrypoint: string;
  port: number;
  status: string;
  domain_name: string;
  last_error?: string;
}

interface DomainRow {
  id: number;
  name: string;
  domain_type: string;
}

type StatusFilter = "all" | "running" | "stopped" | "error";

function statusMeta(status: string) {
  if (status === "running") {
    return {
      label: "En cours",
      bar: "bg-emerald-500",
      badge:
        "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:ring-emerald-800",
    };
  }
  if (status === "error") {
    return {
      label: "Erreur",
      bar: "bg-cp-danger",
      badge: "bg-red-50 text-red-800 ring-red-200 dark:bg-red-950/40 dark:text-red-300 dark:ring-red-900",
    };
  }
  return {
    label: "Arrêtée",
    bar: "bg-slate-400",
    badge: "bg-slate-100 text-slate-700 ring-slate-200 dark:bg-ink-900 dark:text-ink-200 dark:ring-ink-700",
  };
}

function frameworkLabel(fw: string) {
  const map: Record<string, string> = {
    express: "Express",
    nest: "NestJS",
    next: "Next.js",
    generic: "Node",
  };
  return map[fw] || fw;
}

const FRAMEWORKS = [
  { value: "express", label: "Express", hint: "API HTTP classique" },
  { value: "nest", label: "NestJS", hint: "Architecture modulaire" },
  { value: "next", label: "Next.js", hint: "SSR / React" },
  { value: "generic", label: "Generic", hint: "server.js libre" },
] as const;

function AppCard({
  app,
  domains,
  busy,
  domainBusy,
  onAction,
  onLogs,
  onRemove,
  onDomainChange,
}: {
  app: NodeAppItem;
  domains: DomainRow[];
  busy: boolean;
  domainBusy: boolean;
  onAction: (op: string) => void;
  onLogs: () => void;
  onRemove: () => void;
  onDomainChange: (domainName: string) => void;
}) {
  const st = statusMeta(app.status);
  const running = app.status === "running";
  const domainInList = !app.domain_name || domains.some((d) => d.name === app.domain_name);

  return (
    <article className="overflow-hidden rounded-lg border border-cp-border bg-white transition hover:border-cp-link/30 dark:border-ink-800 dark:bg-ink-950">
      <div className={`h-0.5 w-full ${st.bar}`} />
      <div className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <h3 className="truncate text-sm font-semibold text-cp-navy dark:text-ink-50">
              {app.label || app.name}
            </h3>
            {app.label && app.label !== app.name && (
              <span className="font-mono text-[10px] text-cp-muted">{app.name}</span>
            )}
            <span
              className={`inline-flex items-center rounded px-1.5 py-px text-[10px] font-medium ring-1 ring-inset ${st.badge}`}
            >
              {st.label}
            </span>
            <span className="inline-flex items-center gap-0.5 rounded bg-cp-canvas px-1.5 py-px text-[10px] text-cp-muted dark:bg-ink-900">
              <Package className="h-2.5 w-2.5 text-cp-orange" />
              {frameworkLabel(app.framework)}
            </span>
            <span className="rounded bg-cp-canvas px-1.5 py-px font-mono text-[10px] text-cp-muted dark:bg-ink-900">
              node{app.node_version} · :{app.port}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <Globe2 className="h-3 w-3 shrink-0 text-cp-muted" />
            <select
              className="vz-input !min-h-0 max-w-[min(100%,16rem)] !rounded-md !py-0.5 !pl-1.5 !pr-6 text-[11px]"
              value={app.domain_name}
              disabled={domainBusy}
              onChange={(e) => onDomainChange(e.target.value)}
              title="Domaine proxifié vers cette app"
            >
              <option value="">— Aucun domaine —</option>
              {!domainInList && app.domain_name && (
                <option value={app.domain_name}>{app.domain_name} (actuel)</option>
              )}
              {domains.map((d) => (
                <option key={d.id} value={d.name}>
                  {d.name}
                </option>
              ))}
            </select>
            {app.domain_name && (
              <a
                href={`http://${app.domain_name}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-6 w-6 items-center justify-center rounded-md text-cp-link hover:bg-cp-link-soft"
                title="Ouvrir le site"
              >
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
            <span
              className="inline-flex min-w-0 max-w-full items-center gap-1 truncate font-mono text-[10px] text-cp-muted"
              title={app.relative_root}
            >
              <FolderOpen className="h-3 w-3 shrink-0 text-cp-orange" />
              {app.relative_root}
            </span>
          </div>

          {app.last_error && app.status === "error" && (
            <p className="rounded border border-red-200 bg-red-50 px-2 py-1 font-mono text-[10px] text-cp-danger dark:border-red-900 dark:bg-red-950/30">
              {app.last_error}
            </p>
          )}
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-1 self-start sm:self-center">
          {busy ? (
            <span className="inline-flex h-7 w-7 items-center justify-center">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-cp-orange" />
            </span>
          ) : running ? (
            <IconAction label="Arrêter" tone="warning" size="sm" onClick={() => onAction("stop")}>
              <Square className="h-3.5 w-3.5 fill-current" />
            </IconAction>
          ) : (
            <IconAction label="Démarrer" tone="success" size="sm" onClick={() => onAction("start")}>
              <Play className="h-3.5 w-3.5 fill-current" />
            </IconAction>
          )}
          <IconAction
            label="Redémarrer"
            tone="info"
            size="sm"
            disabled={busy}
            onClick={() => onAction("restart")}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </IconAction>
          <IconAction
            label="npm install"
            size="sm"
            disabled={busy}
            onClick={() => onAction("install")}
          >
            <Download className="h-3.5 w-3.5" />
          </IconAction>
          <IconAction label="Logs" size="sm" onClick={onLogs}>
            <FileText className="h-3.5 w-3.5" />
          </IconAction>
          <IconAction label="Supprimer" danger size="sm" onClick={onRemove}>
            <Trash2 className="h-3.5 w-3.5" />
          </IconAction>
        </div>
      </div>
    </article>
  );
}

const EMPTY_FORM = {
  name: "",
  framework: "express",
  node_version: "20",
  domain_name: "",
  relative_root: "",
};

export function NodeAppsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["node-overview"],
    queryFn: () => apiRequest<NodeOverview>("/node/overview/"),
  });
  const { data: apps = [], isLoading } = useQuery({
    queryKey: ["node-apps"],
    queryFn: () => apiRequest<NodeAppItem[]>("/node/apps/"),
  });
  const { data: domains = [] } = useQuery({
    queryKey: ["domains-for-node"],
    queryFn: () => apiRequest<DomainRow[]>("/domains/"),
  });

  const [form, setForm] = useState(EMPTY_FORM);
  const [logs, setLogs] = useState<Record<string, string> | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");

  const domainOptions = useMemo(() => {
    const usable = domains.filter((d) =>
      ["primary", "addon", "subdomain"].includes(d.domain_type),
    );
    return usable.sort((a, b) => a.name.localeCompare(b.name));
  }, [domains]);

  const filteredApps = useMemo(() => {
    const q = query.trim().toLowerCase();
    return apps.filter((app) => {
      if (statusFilter !== "all" && app.status !== statusFilter) return false;
      if (!q) return true;
      return (
        app.name.toLowerCase().includes(q) ||
        app.label.toLowerCase().includes(q) ||
        app.domain_name.toLowerCase().includes(q) ||
        app.relative_root.toLowerCase().includes(q) ||
        app.framework.toLowerCase().includes(q)
      );
    });
  }, [apps, query, statusFilter]);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["node-overview"] });
    void qc.invalidateQueries({ queryKey: ["node-apps"] });
  };

  const create = useMutation({
    mutationFn: () =>
      runWithProgress(
        `Création app Node · ${form.name || "app"}`,
        () =>
          apiRequest("/node/apps/", {
            method: "POST",
            body: JSON.stringify({
              name: form.name,
              framework: form.framework,
              node_version: form.node_version,
              domain_name: form.domain_name,
              relative_root: form.relative_root.trim() || undefined,
            }),
          }),
        {
          tickDetail: (ms) =>
            ms < 2500 ? "Préparation du runtime…" : "Configuration du process…",
        },
      ),
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setError(null);
      setCreateOpen(false);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const action = useMutation({
    mutationFn: ({ id, op, name }: { id: number; op: string; name: string }) =>
      runWithProgress(`Node ${op} · ${name}`, () =>
        apiRequest(`/node/apps/${id}/${op}/`, { method: "POST", body: "{}" }),
      ),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/node/apps/${id}/?remove_files=false`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const loadLogs = useMutation({
    mutationFn: (id: number) => apiRequest<Record<string, string>>(`/node/apps/${id}/logs/`),
    onSuccess: (data) => setLogs(data),
    onError: (err: Error) => setError(err.message),
  });

  const updateDomain = useMutation({
    mutationFn: ({ id, domain_name, name }: { id: number; domain_name: string; name: string }) =>
      runWithProgress(`Domaine · ${name}`, () =>
        apiRequest(`/node/apps/${id}/`, {
          method: "PATCH",
          body: JSON.stringify({ domain_name }),
        }),
      ),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message),
  });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  return (
    <div className="space-y-3 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Créez une app Node, liez un domaine, npm install, puis démarrez."
        actions={
          <button
            type="button"
            className="vz-btn-primary !px-3 !py-1.5 text-xs"
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="h-3.5 w-3.5" />
            Nouvelle app
          </button>
        }
      />

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-cp-danger dark:border-red-900 dark:bg-red-950/30">
          {error}
        </p>
      )}

      <div className="overflow-hidden rounded-lg border border-cp-border bg-white dark:border-ink-800 dark:bg-ink-950">
        <div className="flex flex-col gap-2 border-b border-cp-border px-3 py-2 dark:border-ink-800 sm:flex-row sm:items-center sm:justify-between">
          <Tabs
            tabs={[
              { id: "all", label: "Toutes", count: apps.length },
              {
                id: "running",
                label: "En cours",
                count: apps.filter((a) => a.status === "running").length,
              },
              {
                id: "stopped",
                label: "Arrêtées",
                count: apps.filter((a) => a.status === "stopped").length,
              },
              {
                id: "error",
                label: "Erreurs",
                count: apps.filter((a) => a.status === "error").length,
              },
            ]}
            active={statusFilter}
            onChange={(id) => setStatusFilter(id as StatusFilter)}
          />
          <div className="relative min-w-[160px] flex-1 sm:max-w-[14rem]">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-cp-muted" />
            <input
              className="vz-input !py-1 pl-7 text-xs"
              placeholder="Rechercher…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>

        <div className="space-y-2 p-2.5">
          {isLoading && (
            <div className="flex items-center gap-2 py-6 text-xs text-cp-muted">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-cp-orange" />
              Chargement…
            </div>
          )}

          {!isLoading && apps.length === 0 && (
            <EmptyState
              icon={<Package className="h-7 w-7" />}
              message="Aucune application Node.js."
              action={
                <button
                  type="button"
                  className="vz-btn-primary !px-3 !py-1.5 text-xs"
                  onClick={() => setCreateOpen(true)}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Créer
                </button>
              }
            />
          )}

          {!isLoading && apps.length > 0 && filteredApps.length === 0 && (
            <EmptyState
              icon={<Search className="h-7 w-7" />}
              message="Aucun résultat."
              action={
                <button
                  type="button"
                  className="vz-btn-ghost !py-1 text-xs"
                  onClick={() => {
                    setQuery("");
                    setStatusFilter("all");
                  }}
                >
                  Réinitialiser
                </button>
              }
            />
          )}

          {filteredApps.map((app) => (
            <AppCard
              key={app.id}
              app={app}
              domains={domainOptions}
              busy={action.isPending && action.variables?.id === app.id}
              domainBusy={updateDomain.isPending && updateDomain.variables?.id === app.id}
              onAction={(op) => action.mutate({ id: app.id, op, name: app.name })}
              onLogs={() => loadLogs.mutate(app.id)}
              onDomainChange={(domain_name) =>
                updateDomain.mutate({ id: app.id, domain_name, name: app.name })
              }
              onRemove={() => {
                if (window.confirm(`Supprimer ${app.name} ? Les fichiers sont conservés.`)) {
                  remove.mutate(app.id);
                }
              }}
            />
          ))}
        </div>
      </div>

      {createOpen && (
        <Modal
          wide
          title="Créer une application Node.js"
          subtitle={`Home : ${overview?.home_path || "~/"}`}
          onClose={() => {
            if (!create.isPending) setCreateOpen(false);
          }}
        >
          <form className="space-y-4" onSubmit={onCreate}>
            <div className="space-y-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-cp-muted">
                Framework
              </p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {FRAMEWORKS.map((fw) => {
                  const active = form.framework === fw.value;
                  return (
                    <button
                      key={fw.value}
                      type="button"
                      className={`rounded-lg border px-3 py-2 text-left transition ${
                        active
                          ? "border-cp-orange bg-orange-50 ring-1 ring-cp-orange/30 dark:bg-orange-950/20"
                          : "border-cp-border hover:border-cp-link/40 dark:border-ink-700"
                      }`}
                      onClick={() => setForm({ ...form, framework: fw.value })}
                    >
                      <p className="text-sm font-semibold text-cp-navy dark:text-ink-50">{fw.label}</p>
                      <p className="mt-0.5 text-[10px] text-cp-muted">{fw.hint}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1">
                <span className="text-[11px] font-medium text-cp-muted">Nom *</span>
                <input
                  className="vz-input"
                  placeholder="api"
                  required
                  autoFocus
                  value={form.name}
                  onChange={(e) => {
                    const name = e.target.value;
                    setForm((prev) => ({
                      ...prev,
                      name,
                      relative_root:
                        !prev.relative_root || prev.relative_root === `nodeapps/${prev.name}`
                          ? name
                            ? `nodeapps/${name}`
                            : ""
                          : prev.relative_root,
                    }));
                  }}
                />
              </label>
              <label className="space-y-1">
                <span className="text-[11px] font-medium text-cp-muted">Version Node</span>
                <select
                  className="vz-input"
                  value={form.node_version}
                  onChange={(e) => setForm({ ...form, node_version: e.target.value })}
                >
                  {["22", "20", "18"].map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="block space-y-1">
              <span className="text-[11px] font-medium text-cp-muted">Application root</span>
              <div className="flex overflow-hidden rounded-lg border border-cp-border focus-within:border-cp-link focus-within:ring-2 focus-within:ring-cp-link/20 dark:border-ink-700">
                <span className="flex max-w-[42%] items-center truncate border-r border-cp-border bg-cp-canvas/80 px-2 font-mono text-[11px] text-cp-muted dark:border-ink-700 dark:bg-ink-900">
                  {(overview?.home_path || "~").replace(/\/$/, "")}/
                </span>
                <input
                  className="vz-input !rounded-none !border-0 !ring-0"
                  placeholder="nodeapps/api"
                  value={form.relative_root}
                  onChange={(e) =>
                    setForm({ ...form, relative_root: e.target.value.replace(/^\/+/, "") })
                  }
                />
              </div>
            </label>

            <label className="block space-y-1">
              <span className="text-[11px] font-medium text-cp-muted">Domaine</span>
              <select
                className="vz-input"
                value={form.domain_name}
                onChange={(e) => setForm({ ...form, domain_name: e.target.value })}
              >
                <option value="">— Aucun (optionnel) —</option>
                {domainOptions.map((d) => (
                  <option key={d.id} value={d.name}>
                    {d.name} ({d.domain_type})
                  </option>
                ))}
              </select>
            </label>

            <div className="flex flex-wrap justify-end gap-2 border-t border-cp-border pt-3 dark:border-ink-800">
              <button
                type="button"
                className="vz-btn-ghost"
                disabled={create.isPending}
                onClick={() => setCreateOpen(false)}
              >
                Annuler
              </button>
              <button className="vz-btn-primary" type="submit" disabled={create.isPending}>
                {create.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                Créer l&apos;application
              </button>
            </div>
          </form>
        </Modal>
      )}

      {logs && (
        <Modal title="Logs de l'application" subtitle="stdout / stderr / npm" onClose={() => setLogs(null)} wide>
          <div className="grid max-h-[60vh] gap-3 overflow-y-auto">
            {Object.entries(logs).map(([name, content]) => (
              <div key={name}>
                <p className="mb-1 font-mono text-[11px] font-semibold text-cp-orange">{name}</p>
                <pre className="max-h-40 overflow-auto rounded-lg border border-cp-border/70 bg-cp-canvas p-3 text-xs dark:border-ink-800 dark:bg-ink-900">
                  {content || "(vide)"}
                </pre>
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
