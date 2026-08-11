import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Plus, Shield, Trash2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";
import type { Domain } from "@/types";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import { EmptyState, PageHeader, StatusDot } from "@/components/ui/PageChrome";

export function DomainsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: domains = [], isLoading, isError: domainsLoadError, error: domainsError } = useQuery({
    queryKey: ["domains"],
    queryFn: () => apiRequest<Domain[]>("/domains/"),
  });

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data: olsInfo } = useQuery({
    queryKey: ["ols-overview"],
    queryFn: () =>
      apiRequest<{
        enabled: boolean;
        installed: boolean;
        ready?: boolean;
        default_engine?: string;
      }>("/server-setup/ols/").catch(() => ({
        enabled: false,
        installed: false,
        ready: false,
        default_engine: "nginx",
      })),
    staleTime: 60_000,
  });
  const olsReady = Boolean(olsInfo?.ready ?? (olsInfo?.enabled && olsInfo?.installed));
  const preferredEngine = olsReady && olsInfo?.default_engine === "ols" ? "ols" : "nginx";

  const [form, setForm] = useState({
    name: "",
    domain_type: "primary",
    ipv4_address: "",
    parent_id: "",
    web_engine: "nginx",
  });
  const [subLabel, setSubLabel] = useState("www");
  const [createOpen, setCreateOpen] = useState(false);
  const [subdomainOpen, setSubdomainOpen] = useState(false);
  const [redirectOpen, setRedirectOpen] = useState(false);
  const [redirect, setRedirect] = useState({
    source_path: "/",
    destination_url: "https://",
    redirect_type: "301",
  });

  useEffect(() => {
    setForm((prev) =>
      prev.web_engine === preferredEngine ? prev : { ...prev, web_engine: preferredEngine },
    );
  }, [preferredEngine]);

  const selected = useMemo(
    () => domains.find((d) => d.id === selectedId) ?? domains[0] ?? null,
    [domains, selectedId],
  );

  const parents = domains.filter((d) =>
    ["primary", "addon"].includes(d.domain_type),
  );

  const createDomain = useMutation({
    mutationFn: () =>
      apiRequest("/domains/", {
        method: "POST",
        body: JSON.stringify({
          name: form.name.trim(),
          domain_type: form.domain_type,
          ipv4_address: form.ipv4_address.trim() || null,
          parent_id: form.parent_id ? Number(form.parent_id) : null,
          create_dns_zone: true,
          web_engine: form.web_engine,
        }),
      }),
    onSuccess: () => {
      setForm({
        name: "",
        domain_type: "primary",
        ipv4_address: form.ipv4_address,
        parent_id: "",
        web_engine: preferredEngine,
      });
      void qc.invalidateQueries({ queryKey: ["domains"] });
      void qc.invalidateQueries({ queryKey: ["dns-zones"] });
      void qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
      setCreateOpen(false);
    },
  });

  const updateEngine = useMutation({
    mutationFn: ({ id, web_engine }: { id: number; web_engine: string }) =>
      apiRequest(`/domains/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ web_engine }),
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["domains"] }),
  });

  const createSub = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Sélectionnez un domaine");
      return apiRequest<Domain>("/domains/subdomains/", {
        method: "POST",
        body: JSON.stringify({ label: subLabel.trim(), parent_id: selected.id }),
      });
    },
    onSuccess: (created) => {
      setSubLabel("");
      void qc.invalidateQueries({ queryKey: ["domains"] });
      if (created?.id) setSelectedId(created.id);
      setSubdomainOpen(false);
    },
  });

  const createRedirect = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Sélectionnez un domaine");
      return apiRequest(`/domains/${selected.id}/redirects/`, {
        method: "POST",
        body: JSON.stringify(redirect),
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["domains"] });
      setRedirectOpen(false);
    },
  });

  const issueSsl = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Sélectionnez un domaine");
      return runWithProgress(
        `SSL Let's Encrypt · ${selected.name}`,
        () =>
          apiRequest(`/domains/${selected.id}/ssl/letsencrypt/`, {
            method: "POST",
            body: "{}",
          }),
        {
          tickDetail: (ms) =>
            ms < 4000 ? "Challenge ACME…" : "Émission du certificat…",
        },
      );
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["domains"] }),
  });

  const removeDomain = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/domains/${id}/?remove_dns=true`, { method: "DELETE" }),
    onSuccess: () => {
      setSelectedId(null);
      void qc.invalidateQueries({ queryKey: ["domains"] });
      void qc.invalidateQueries({ queryKey: ["dns-zones"] });
    },
  });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    createDomain.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Domaines, alias, sous-domaines, redirections et certificats Let’s Encrypt."
        stats={[
          { label: "Domaines", value: domains.length },
          { label: "SSL actifs", value: domains.filter((d) => d.ssl?.status === "active").length },
        ]}
        actions={
          <button type="button" className="vz-btn-primary" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Ajouter un domaine
          </button>
        }
      />
      {domainsLoadError && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
          Impossible de charger les domaines : {(domainsError as Error)?.message || "erreur API"}
        </p>
      )}
      {createOpen && (
        <Modal title="Ajouter un domaine" subtitle="Une zone DNS est créée automatiquement." onClose={() => setCreateOpen(false)} wide>
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={onCreate}>
            <input className="vz-input sm:col-span-2" placeholder="exemple.com" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <select className="vz-input" value={form.domain_type} onChange={(e) => setForm({ ...form, domain_type: e.target.value })}>
              <option value="primary">Principal</option><option value="addon">Additionnel</option><option value="parked">Parké</option><option value="alias">Alias</option>
            </select>
            <input className="vz-input" placeholder="IPv4 (auto si vide)" value={form.ipv4_address} onChange={(e) => setForm({ ...form, ipv4_address: e.target.value })} />
            <select className="vz-input sm:col-span-2" value={form.parent_id} onChange={(e) => setForm({ ...form, parent_id: e.target.value })}>
              <option value="">Parent (parked/alias)</option>{parents.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <label className="sm:col-span-2 space-y-1">
              <span className="text-[11px] font-medium text-cp-muted">Web engine (PHP / static)</span>
              <select
                className="vz-input"
                value={form.web_engine}
                onChange={(e) => setForm({ ...form, web_engine: e.target.value })}
              >
                <option value="nginx">Nginx + PHP-FPM</option>
                <option value="ols" disabled={!olsReady}>
                  OpenLiteSpeed{olsReady ? "" : " (non installé)"}
                </option>
              </select>
              {!olsReady && (
                <span className="block text-[11px] text-cp-muted">
                  Pour activer OLS : WHM → OpenLiteSpeed (VZONE_OLS_ENABLED=1).
                </span>
              )}
            </label>
            {createDomain.isError && <p className="sm:col-span-2 text-sm text-cp-danger">{(createDomain.error as Error)?.message}</p>}
            <div className="flex justify-end gap-2 sm:col-span-2"><button type="button" className="vz-btn-ghost" onClick={() => setCreateOpen(false)}>Annuler</button><button className="vz-btn-primary" disabled={createDomain.isPending}>Ajouter</button></div>
          </form>
        </Modal>
      )}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className={`vz-panel overflow-hidden ${selected ? "hidden lg:block" : ""}`}>
          <div className="border-b border-cp-border bg-cp-canvas px-3 py-2 text-xs font-semibold uppercase text-cp-muted dark:border-ink-800 dark:bg-ink-900">
            Domaines {isLoading ? "…" : `(${domains.length})`}
          </div>
          <ul>
            {domains.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  className={`block w-full border-b border-cp-border px-3 py-3 text-left text-sm dark:border-ink-800 sm:py-2 ${
                    selected?.id === d.id ? "bg-cp-orange-soft font-semibold text-cp-orange-dark" : ""
                  }`}
                  onClick={() => setSelectedId(d.id)}
                >
                  {d.name}
                  <span className="mt-0.5 block text-[11px] font-normal capitalize text-cp-muted">
                    {d.domain_type}
                    {d.ssl?.status ? ` · SSL ${d.ssl.status}` : ""}
                  </span>
                </button>
              </li>
            ))}
            {!isLoading && domains.length === 0 && <li><EmptyState icon={<ExternalLink className="h-5 w-5" />} message="Aucun domaine configuré." /></li>}
          </ul>
        </div>

        {selected ? (
          <div className="space-y-3">
            <button
              type="button"
              className="vz-btn-ghost vz-btn-sm lg:hidden"
              onClick={() => setSelectedId(null)}
            >
              ← Domaines
            </button>
            <div className="vz-panel p-3 sm:p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-lg font-semibold">{selected.name}</p>
                  <p className="mt-1 text-xs text-cp-muted">
                    Type <span className="capitalize">{selected.domain_type}</span>
                    {" · "}
                    Zone DNS {selected.dns_zone_name ?? "—"}
                  </p>
                  <p className="mt-2 rounded-md border border-cp-border bg-cp-canvas/60 px-3 py-2 font-mono text-xs text-cp-text dark:border-ink-700 dark:bg-ink-900">
                    Document root : {selected.document_root || "—"}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <label className="text-[11px] font-medium text-cp-muted">Web engine</label>
                    <select
                      className="vz-input !min-h-0 max-w-[14rem] !py-1 text-xs"
                      value={selected.web_engine || "nginx"}
                      disabled={updateEngine.isPending}
                      onChange={(e) =>
                        updateEngine.mutate({ id: selected.id, web_engine: e.target.value })
                      }
                    >
                      <option value="nginx">Nginx + PHP-FPM</option>
                      <option value="ols" disabled={!olsReady && selected.web_engine !== "ols"}>
                        OpenLiteSpeed
                      </option>
                    </select>
                    {updateEngine.isError && (
                      <span className="text-[11px] text-cp-danger">
                        {(updateEngine.error as Error)?.message}
                      </span>
                    )}
                  </div>
                  {selected.domain_type === "subdomain" ? (
                    <p className="mt-1 text-xs text-cp-muted">
                      Placez un <code className="font-mono">index.html</code> ou{" "}
                      <code className="font-mono">index.php</code> dans ce dossier (File Manager) :
                      ce sera le site affiché pour {selected.name}.
                    </p>
                  ) : null}
                  {selected.ssl && (
                    <div className="mt-2"><StatusDot status={selected.ssl.status} label={`SSL ${selected.ssl.status} · ${selected.ssl.provider}`} />
                      {selected.ssl.expires_at
                        ? <span className="ml-2 text-xs text-cp-muted">expire {new Date(selected.ssl.expires_at).toLocaleDateString("fr-FR")}</span>
                        : ""}</div>
                  )}
                  {selected.ssl?.last_error ? (
                    <p className="mt-1 text-xs text-cp-danger">{selected.ssl.last_error}</p>
                  ) : null}
                </div>
                <div className="flex gap-1">
                  <IconAction label="Émettre le certificat Let’s Encrypt" onClick={() => issueSsl.mutate()} disabled={issueSsl.isPending}><Shield className="h-4 w-4" /></IconAction>
                  <IconAction label="Supprimer le domaine" danger onClick={() => removeDomain.mutate(selected.id)}><Trash2 className="h-4 w-4" /></IconAction>
                </div>
              </div>
            </div>

            {["primary", "addon"].includes(selected.domain_type) && (
              <div className="vz-panel flex items-center justify-between p-4"><div><p className="font-medium">Sous-domaines</p><p className="text-xs text-cp-muted">Crée un répertoire et un index pour le nouveau site.</p></div><button className="vz-btn-secondary" onClick={() => setSubdomainOpen(true)}><Plus className="h-4 w-4" /> Ajouter</button></div>
            )}

            <div className="vz-panel flex items-center justify-between p-4"><div><p className="font-medium">Redirections</p><p className="text-xs text-cp-muted">{selected.redirects.length} configurée{selected.redirects.length > 1 ? "s" : ""}</p></div><button className="vz-btn-secondary" onClick={() => setRedirectOpen(true)}><Plus className="h-4 w-4" /> Ajouter</button></div>

            {selected.redirects.length > 0 && (
              <div className="vz-panel overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
                    <tr>
                      <th className="px-3 py-2">Source</th>
                      <th className="px-3 py-2">Destination</th>
                      <th className="px-3 py-2">Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.redirects.map((r) => (
                      <tr key={r.id} className="border-t border-cp-border dark:border-ink-800">
                        <td className="px-3 py-2 font-mono text-xs">{r.source_path}</td>
                        <td className="px-3 py-2 font-mono text-xs">{r.destination_url}</td>
                        <td className="px-3 py-2">{r.redirect_type}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          <div className="vz-panel"><EmptyState icon={<ExternalLink className="h-5 w-5" />} message="Sélectionnez un domaine pour afficher ses réglages." /></div>
        )}
      </div>
      {subdomainOpen && selected && <Modal title="Créer un sous-domaine" onClose={() => setSubdomainOpen(false)}><form className="space-y-3" onSubmit={(e) => { e.preventDefault(); createSub.mutate(); }}><p className="text-sm text-cp-muted">Le sous-domaine pointera vers son propre répertoire.</p><div className="flex items-center gap-2"><input className="vz-input" value={subLabel} onChange={(e) => setSubLabel(e.target.value)} placeholder="blog" required /><span className="text-sm text-cp-muted">.{selected.name}</span></div>{createSub.isError && <p className="text-sm text-cp-danger">{(createSub.error as Error)?.message}</p>}<div className="flex justify-end gap-2"><button type="button" className="vz-btn-ghost" onClick={() => setSubdomainOpen(false)}>Annuler</button><button className="vz-btn-primary" disabled={createSub.isPending}>Créer</button></div></form></Modal>}
      {redirectOpen && selected && <Modal title="Ajouter une redirection" onClose={() => setRedirectOpen(false)}><form className="space-y-3" onSubmit={(e) => { e.preventDefault(); createRedirect.mutate(); }}><input className="vz-input w-full" value={redirect.source_path} onChange={(e) => setRedirect({ ...redirect, source_path: e.target.value })} placeholder="/chemin" /><input className="vz-input w-full" value={redirect.destination_url} onChange={(e) => setRedirect({ ...redirect, destination_url: e.target.value })} placeholder="https://destination" required />{createRedirect.isError && <p className="text-sm text-cp-danger">{(createRedirect.error as Error)?.message}</p>}<div className="flex justify-end gap-2"><button type="button" className="vz-btn-ghost" onClick={() => setRedirectOpen(false)}>Annuler</button><button className="vz-btn-primary" disabled={createRedirect.isPending}>Ajouter</button></div></form></Modal>}
    </div>
  );
}
