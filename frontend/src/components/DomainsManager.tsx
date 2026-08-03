import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";
import type { Domain } from "@/types";

export function DomainsManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: domains = [], isLoading } = useQuery({
    queryKey: ["domains"],
    queryFn: () => apiRequest<Domain[]>("/domains/"),
  });

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [form, setForm] = useState({
    name: "",
    domain_type: "primary",
    ipv4_address: "",
    parent_id: "",
  });
  const [subLabel, setSubLabel] = useState("www");
  const [redirect, setRedirect] = useState({
    source_path: "/",
    destination_url: "https://",
    redirect_type: "301",
  });

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
          name: form.name,
          domain_type: form.domain_type,
          ipv4_address: form.ipv4_address || null,
          parent_id: form.parent_id ? Number(form.parent_id) : null,
          create_dns_zone: true,
        }),
      }),
    onSuccess: () => {
      setForm({ name: "", domain_type: "primary", ipv4_address: "", parent_id: "" });
      void qc.invalidateQueries({ queryKey: ["domains"] });
      void qc.invalidateQueries({ queryKey: ["dns-zones"] });
      void qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
  });

  const createSub = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Sélectionnez un domaine");
      return apiRequest("/domains/subdomains/", {
        method: "POST",
        body: JSON.stringify({ label: subLabel, parent_id: selected.id }),
      });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["domains"] }),
  });

  const createRedirect = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Sélectionnez un domaine");
      return apiRequest(`/domains/${selected.id}/redirects/`, {
        method: "POST",
        body: JSON.stringify(redirect),
      });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["domains"] }),
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
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-cp-muted">
          Domaines, addon, parked, alias, sous-domaines, redirections et SSL Let&apos;s Encrypt.
        </p>
      </div>

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-6" onSubmit={onCreate}>
        <input
          className="vz-input md:col-span-2"
          placeholder="exemple.com"
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <select
          className="vz-input"
          value={form.domain_type}
          onChange={(e) => setForm({ ...form, domain_type: e.target.value })}
        >
          <option value="primary">Primary</option>
          <option value="addon">Addon</option>
          <option value="parked">Parked</option>
          <option value="alias">Alias</option>
        </select>
        <input
          className="vz-input"
          placeholder="IPv4"
          value={form.ipv4_address}
          onChange={(e) => setForm({ ...form, ipv4_address: e.target.value })}
        />
        <select
          className="vz-input"
          value={form.parent_id}
          onChange={(e) => setForm({ ...form, parent_id: e.target.value })}
        >
          <option value="">Parent (parked/alias)</option>
          {parents.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button className="vz-btn-primary" type="submit" disabled={createDomain.isPending}>
          Ajouter
        </button>
      </form>

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="vz-panel overflow-hidden">
          <div className="border-b border-cp-border bg-cp-canvas px-3 py-2 text-xs font-semibold uppercase text-cp-muted dark:border-ink-800 dark:bg-ink-900">
            Domaines {isLoading ? "…" : `(${domains.length})`}
          </div>
          <ul>
            {domains.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  className={`block w-full border-b border-cp-border px-3 py-2 text-left text-sm dark:border-ink-800 ${
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
          </ul>
        </div>

        {selected ? (
          <div className="space-y-3">
            <div className="vz-panel p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-lg font-semibold">{selected.name}</p>
                  <p className="text-xs text-cp-muted">
                    Type {selected.domain_type} · Zone DNS {selected.dns_zone_name ?? "—"} · Docroot{" "}
                    {selected.document_root || "—"}
                  </p>
                  {selected.ssl && (
                    <p className="mt-2 text-sm">
                      SSL : <strong>{selected.ssl.status}</strong> ({selected.ssl.provider})
                      {selected.ssl.expires_at
                        ? ` · expire ${new Date(selected.ssl.expires_at).toLocaleDateString("fr-FR")}`
                        : ""}
                    </p>
                  )}
                  {selected.ssl?.last_error ? (
                    <p className="mt-1 text-xs text-cp-danger">{selected.ssl.last_error}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="vz-btn-primary"
                    onClick={() => issueSsl.mutate()}
                    disabled={issueSsl.isPending}
                  >
                    Let&apos;s Encrypt
                  </button>
                  <button
                    type="button"
                    className="vz-btn-ghost text-cp-danger"
                    onClick={() => removeDomain.mutate(selected.id)}
                  >
                    Supprimer
                  </button>
                </div>
              </div>
            </div>

            {["primary", "addon"].includes(selected.domain_type) && (
              <form
                className="vz-panel flex flex-wrap gap-2 p-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  createSub.mutate();
                }}
              >
                <input
                  className="vz-input max-w-[160px]"
                  value={subLabel}
                  onChange={(e) => setSubLabel(e.target.value)}
                  placeholder="sous-domaine"
                />
                <span className="self-center text-sm text-cp-muted">.{selected.name}</span>
                <button className="vz-btn-ghost" type="submit">
                  Créer sous-domaine
                </button>
              </form>
            )}

            <form
              className="vz-panel grid gap-2 p-4 md:grid-cols-4"
              onSubmit={(e) => {
                e.preventDefault();
                createRedirect.mutate();
              }}
            >
              <input
                className="vz-input"
                value={redirect.source_path}
                onChange={(e) => setRedirect({ ...redirect, source_path: e.target.value })}
                placeholder="/chemin"
              />
              <input
                className="vz-input md:col-span-2"
                value={redirect.destination_url}
                onChange={(e) => setRedirect({ ...redirect, destination_url: e.target.value })}
                placeholder="https://destination"
                required
              />
              <button className="vz-btn-ghost" type="submit">
                Ajouter redirection
              </button>
            </form>

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
          <div className="vz-panel p-6 text-sm text-cp-muted">Aucun domaine sélectionné.</div>
        )}
      </div>
    </div>
  );
}
