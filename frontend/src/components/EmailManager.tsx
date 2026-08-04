import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Mail } from "lucide-react";
import { apiRequest } from "@/lib/api";

interface MailOverview {
  domains: number;
  mailboxes: number;
  active_mailboxes: number;
  forwarders: number;
  webmail_url: string;
}

interface MailDomain {
  id: number;
  name: string;
  max_quota_mb: number;
  dkim_enabled: boolean;
  dkim_selector: string;
  spf_record: string;
  dmarc_policy: string;
  mailbox_count: number;
  is_active: boolean;
}

interface Mailbox {
  id: number;
  mail_domain: number;
  domain_name: string;
  local_part: string;
  address: string;
  quota_mb: number;
  used_mb: number;
  status: string;
  is_suspended: boolean;
}

interface MailForwarder {
  id: number;
  mail_domain: number;
  local_part: string;
  address: string;
  destinations: string[];
  keep_copy: boolean;
}

export function EmailManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["email-overview"],
    queryFn: () => apiRequest<MailOverview>("/email/overview/"),
  });
  const { data: domains = [] } = useQuery({
    queryKey: ["email-domains"],
    queryFn: () => apiRequest<MailDomain[]>("/email/domains/"),
  });
  const { data: mailboxes = [], isLoading } = useQuery({
    queryKey: ["email-mailboxes"],
    queryFn: () => apiRequest<Mailbox[]>("/email/mailboxes/"),
  });
  const { data: forwarders = [] } = useQuery({
    queryKey: ["email-forwarders"],
    queryFn: () => apiRequest<MailForwarder[]>("/email/forwarders/"),
  });

  const [domainForm, setDomainForm] = useState({ name: "", max_quota_mb: 1024 });
  const [boxForm, setBoxForm] = useState({
    mail_domain_id: 0,
    local_part: "",
    password: "",
    quota_mb: 250,
  });
  const [fwdForm, setFwdForm] = useState({
    mail_domain_id: 0,
    local_part: "",
    destinations: "",
    keep_copy: false,
  });
  const [error, setError] = useState<string | null>(null);
  const [resetPwd, setResetPwd] = useState<{ id: number; address: string; password: string } | null>(
    null,
  );

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["email-overview"] });
    void qc.invalidateQueries({ queryKey: ["email-domains"] });
    void qc.invalidateQueries({ queryKey: ["email-mailboxes"] });
    void qc.invalidateQueries({ queryKey: ["email-forwarders"] });
  };

  const createDomain = useMutation({
    mutationFn: () =>
      apiRequest("/email/domains/", {
        method: "POST",
        body: JSON.stringify({ ...domainForm, enable_dns: true }),
      }),
    onSuccess: () => {
      setDomainForm({ name: "", max_quota_mb: 1024 });
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const createBox = useMutation({
    mutationFn: (payload: typeof boxForm) =>
      apiRequest("/email/mailboxes/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setBoxForm((f) => ({ ...f, local_part: "", password: "" }));
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const createFwd = useMutation({
    mutationFn: (payload: {
      mail_domain_id: number;
      local_part: string;
      destinations: string[];
      keep_copy: boolean;
    }) =>
      apiRequest("/email/forwarders/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setFwdForm((f) => ({ ...f, local_part: "", destinations: "" }));
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const suspend = useMutation({
    mutationFn: ({ id, suspended }: { id: number; suspended: boolean }) =>
      apiRequest(`/email/mailboxes/${id}/suspend/`, {
        method: "POST",
        body: JSON.stringify({ suspended }),
      }),
    onSuccess: invalidateAll,
  });

  const removeBox = useMutation({
    mutationFn: (id: number) => apiRequest(`/email/mailboxes/${id}/`, { method: "DELETE" }),
    onSuccess: invalidateAll,
  });

  const removeFwd = useMutation({
    mutationFn: (id: number) => apiRequest(`/email/forwarders/${id}/`, { method: "DELETE" }),
    onSuccess: invalidateAll,
  });

  const enableDkim = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/email/domains/${id}/dkim/`, {
        method: "POST",
        body: JSON.stringify({ selector: "default" }),
      }),
    onSuccess: invalidateAll,
    onError: (err: Error) => setError(err.message),
  });

  const syncDns = useMutation({
    mutationFn: (id: number) =>
      apiRequest(`/email/domains/${id}/dns-sync/`, { method: "POST", body: "{}" }),
    onSuccess: invalidateAll,
    onError: (err: Error) => setError(err.message),
  });

  const openWebmail = useMutation({
    mutationFn: (mailboxId: number) =>
      apiRequest<{ url: string; address: string }>("/email/webmail/sso/", {
        method: "POST",
        body: JSON.stringify({ mailbox_id: mailboxId }),
      }),
    onSuccess: (data) => {
      setError(null);
      const raw = data.url || "";
      const url = raw.startsWith("http")
        ? raw
        : `${window.location.origin}${raw.startsWith("/") ? "" : "/"}${raw}`;
      const popup = window.open(url, "_blank", "noopener,noreferrer");
      if (!popup) {
        window.location.assign(url);
      }
    },
    onError: (err: Error) => setError(err.message),
  });

  const changePassword = useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) =>
      apiRequest(`/email/mailboxes/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ password }),
      }),
    onSuccess: () => {
      setResetPwd(null);
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const selectedDomainId = boxForm.mail_domain_id || domains[0]?.id || 0;
  const selectedFwdDomainId = fwdForm.mail_domain_id || domains[0]?.id || 0;

  function onCreateDomain(e: FormEvent) {
    e.preventDefault();
    createDomain.mutate();
  }

  function onCreateBox(e: FormEvent) {
    e.preventDefault();
    if (!selectedDomainId) {
      setError("Créez d'abord un domaine mail.");
      return;
    }
    const payload = { ...boxForm, mail_domain_id: selectedDomainId };
    setBoxForm(payload);
    createBox.mutate(payload);
  }

  function onCreateFwd(e: FormEvent) {
    e.preventDefault();
    if (!selectedFwdDomainId) {
      setError("Créez d'abord un domaine mail.");
      return;
    }
    setFwdForm((f) => ({ ...f, mail_domain_id: selectedFwdDomainId }));
    createFwd.mutate({
      mail_domain_id: selectedFwdDomainId,
      local_part: fwdForm.local_part,
      destinations: fwdForm.destinations
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      keep_copy: fwdForm.keep_copy,
    });
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{title}</h1>
            <p className="text-sm text-cp-muted">
              Domaines mail, boîtes, redirections, SPF / DKIM / DMARC — webmail Roundcube.
            </p>
            <p className="mt-1 text-xs text-cp-muted">
              Connexion Roundcube : utilisez l&apos;adresse <strong>complète</strong>{" "}
              (<code className="font-mono">local@domaine.tld</code>) et le mot de passe de la
              boîte — pas le compte panel.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {overview?.webmail_url && (
              <a
                className="vz-btn-ghost"
                href={overview.webmail_url}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink className="h-4 w-4" />
                Roundcube
              </a>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Domaines", value: overview?.domains ?? "—" },
          { label: "Boîtes", value: overview?.mailboxes ?? "—" },
          { label: "Actives", value: overview?.active_mailboxes ?? "—" },
          { label: "Forwarders", value: overview?.forwarders ?? "—" },
        ].map((card) => (
          <div key={card.label} className="vz-panel p-4">
            <p className="text-xs font-semibold uppercase text-cp-muted">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold text-cp-orange">{card.value}</p>
          </div>
        ))}
      </div>

      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">{error}</p>
      )}

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-4" onSubmit={onCreateDomain}>
        <input
          className="vz-input md:col-span-2"
          placeholder="domaine (ex: exemple.com)"
          required
          value={domainForm.name}
          onChange={(e) => setDomainForm({ ...domainForm, name: e.target.value })}
        />
        <input
          className="vz-input"
          type="number"
          min={1}
          title="Quota max Mo"
          value={domainForm.max_quota_mb}
          onChange={(e) => setDomainForm({ ...domainForm, max_quota_mb: Number(e.target.value) })}
        />
        <button className="vz-btn-primary" type="submit" disabled={createDomain.isPending}>
          Ajouter domaine
        </button>
      </form>

      {domains.length > 0 && (
        <div className="vz-panel overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
              <tr>
                <th className="px-3 py-2">Domaine</th>
                <th className="px-3 py-2">Boîtes</th>
                <th className="px-3 py-2">DKIM</th>
                <th className="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {domains.map((d) => (
                <tr key={d.id} className="border-t border-cp-border dark:border-ink-800">
                  <td className="px-3 py-2 font-medium">{d.name}</td>
                  <td className="px-3 py-2">{d.mailbox_count}</td>
                  <td className="px-3 py-2">{d.dkim_enabled ? "oui" : "non"}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-2">
                      {!d.dkim_enabled && (
                        <button
                          type="button"
                          className="text-cp-link hover:underline"
                          onClick={() => enableDkim.mutate(d.id)}
                        >
                          Activer DKIM
                        </button>
                      )}
                      <button
                        type="button"
                        className="text-cp-link hover:underline"
                        onClick={() => syncDns.mutate(d.id)}
                      >
                        Sync DNS
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-5" onSubmit={onCreateBox}>
        <select
          className="vz-input"
          value={selectedDomainId}
          onChange={(e) => setBoxForm({ ...boxForm, mail_domain_id: Number(e.target.value) })}
        >
          {domains.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <input
          className="vz-input"
          placeholder="local (ex: info)"
          required
          value={boxForm.local_part}
          onChange={(e) => setBoxForm({ ...boxForm, local_part: e.target.value })}
        />
        <input
          className="vz-input"
          type="password"
          placeholder="mot de passe"
          required
          minLength={8}
          value={boxForm.password}
          onChange={(e) => setBoxForm({ ...boxForm, password: e.target.value })}
        />
        <input
          className="vz-input"
          type="number"
          min={1}
          title="Quota Mo"
          value={boxForm.quota_mb}
          onChange={(e) => setBoxForm({ ...boxForm, quota_mb: Number(e.target.value) })}
        />
        <button className="vz-btn-primary" type="submit" disabled={createBox.isPending}>
          Créer boîte
        </button>
      </form>

      <div className="vz-panel overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Adresse</th>
              <th className="px-3 py-2">Quota</th>
              <th className="px-3 py-2">État</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={4}>
                  Chargement…
                </td>
              </tr>
            )}
            {mailboxes.map((box) => (
              <tr key={box.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-mono text-xs">{box.address}</td>
                <td className="px-3 py-2">
                  {box.used_mb}/{box.quota_mb} Mo
                </td>
                <td className="px-3 py-2">
                  <span
                    className={
                      box.status === "active"
                        ? "text-cp-success"
                        : box.status === "suspended"
                          ? "text-cp-danger"
                          : "text-cp-muted"
                    }
                  >
                    {box.status}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 text-cp-link hover:underline disabled:opacity-50"
                      disabled={box.status !== "active" || openWebmail.isPending}
                      onClick={() => openWebmail.mutate(box.id)}
                      title="Ouvrir Roundcube authentifié"
                    >
                      <Mail className="h-3.5 w-3.5" />
                      Webmail
                    </button>
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() =>
                        setResetPwd({ id: box.id, address: box.address, password: "" })
                      }
                    >
                      Mot de passe
                    </button>
                    <button
                      type="button"
                      className="text-cp-link hover:underline"
                      onClick={() =>
                        suspend.mutate({ id: box.id, suspended: !box.is_suspended })
                      }
                    >
                      {box.is_suspended ? "Réactiver" : "Suspendre"}
                    </button>
                    <button
                      type="button"
                      className="text-cp-danger hover:underline"
                      onClick={() => {
                        if (window.confirm(`Supprimer ${box.address} ?`)) removeBox.mutate(box.id);
                      }}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && mailboxes.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={4}>
                  Aucune boîte mail.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-4" onSubmit={onCreateFwd}>
        <select
          className="vz-input"
          value={selectedFwdDomainId}
          onChange={(e) => setFwdForm({ ...fwdForm, mail_domain_id: Number(e.target.value) })}
        >
          {domains.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <input
          className="vz-input"
          placeholder="alias (ex: contact)"
          required
          value={fwdForm.local_part}
          onChange={(e) => setFwdForm({ ...fwdForm, local_part: e.target.value })}
        />
        <input
          className="vz-input"
          placeholder="destinations (séparées par virgule)"
          required
          value={fwdForm.destinations}
          onChange={(e) => setFwdForm({ ...fwdForm, destinations: e.target.value })}
        />
        <button className="vz-btn-primary" type="submit" disabled={createFwd.isPending}>
          Créer forwarder
        </button>
      </form>

      {forwarders.length > 0 && (
        <div className="vz-panel overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
              <tr>
                <th className="px-3 py-2">Adresse</th>
                <th className="px-3 py-2">Vers</th>
                <th className="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {forwarders.map((fwd) => (
                <tr key={fwd.id} className="border-t border-cp-border dark:border-ink-800">
                  <td className="px-3 py-2 font-mono text-xs">{fwd.address}</td>
                  <td className="px-3 py-2 text-xs">{fwd.destinations.join(", ")}</td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      className="text-cp-danger hover:underline"
                      onClick={() => {
                        if (window.confirm(`Supprimer ${fwd.address} ?`)) removeFwd.mutate(fwd.id);
                      }}
                    >
                      Supprimer
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {resetPwd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950">
            <p className="mb-1 font-semibold">Nouveau mot de passe</p>
            <p className="mb-3 text-xs text-cp-muted">{resetPwd.address}</p>
            <input
              className="vz-input mb-3"
              type="password"
              minLength={8}
              placeholder="min. 8 caractères"
              value={resetPwd.password}
              onChange={(e) => setResetPwd({ ...resetPwd, password: e.target.value })}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setResetPwd(null)}>
                Annuler
              </button>
              <button
                type="button"
                className="vz-btn-primary"
                disabled={resetPwd.password.length < 8 || changePassword.isPending}
                onClick={() =>
                  changePassword.mutate({ id: resetPwd.id, password: resetPwd.password })
                }
              >
                Enregistrer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
